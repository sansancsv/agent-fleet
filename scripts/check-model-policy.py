#!/usr/bin/env python3
"""Kiểm ràng buộc "mức nhạy cảm dữ liệu (dataClass) quyết định backend model".

Nguồn sự thật: `policy/model-routing.yaml` → `dataClasses.<mức>.allowedBackends`.
Bốn thứ phải khớp với nó:

  1. `agents.*` của mọi `profiles/*.yaml` — hồ sơ không được khai backend mà
     chính mức dữ liệu của nó không cho phép. Trước khi có phép kiểm này,
     support.yaml (confidential) khai Gemini mà validate.sh vẫn xanh.
  2. `MODEL_POLICY` trong `orchestration/langgraph/src/fleet/policies.py` — bảng
     mà chốt lúc chạy (`assert_backend_allowed`, gọi trong server.py) tra.
  3. `allowed_backends` trong `policy/opa/fleet.rego`.
  4. Backend của từng vai trò: `ROLE_BACKENDS` (acpx_client.py) phải trùng
     `case "$ROLE"` trong `execution-plane/scripts/run-role.sh`. Chốt lúc chạy
     suy ra backend từ ROLE_BACKENDS, còn thứ THẬT SỰ chạy qua agent-runner là
     bảng trong run-role.sh — hai bảng lệch nhau thì chốt kiểm một backend
     trong khi dữ liệu đi tới backend khác.

Đọc file Python bằng `ast` và fleet.rego/run-role.sh bằng regex — KHÔNG import,
KHÔNG gọi opa — để chạy được ở nơi chỉ có python3 + pyyaml (job `validate` của
CI). Không đọc được bảng nào thì báo lỗi: phép kiểm không được lặng lẽ bỏ qua
đúng chỗ nó phải canh (fail closed).

Thành công: in một dòng tóm tắt phạm vi đã kiểm, thoát 0.
Thất bại:   in từng chỗ lệch (thụt hai dấu cách), thoát 1.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

import yaml

ROUTING = "policy/model-routing.yaml"
POLICIES_PY = "orchestration/langgraph/src/fleet/policies.py"
ACPX_CLIENT_PY = "orchestration/langgraph/src/fleet/acpx_client.py"
FLEET_REGO = "policy/opa/fleet.rego"
RUN_ROLE_SH = "execution-plane/scripts/run-role.sh"

# allowed_backends := {
#     "public": {"claude", "codex"},
#     ...
# }
_REGO_BLOCK = re.compile(r"^allowed_backends\s*:=\s*\{(?P<body>.*?)^\s*\}\s*$", re.M | re.S)
_REGO_ENTRY = re.compile(r'"(?P<dc>[^"]+)"\s*:\s*\{(?P<items>[^{}]*)\}')
_QUOTED = re.compile(r'"([^"]*)"')

# case "$ROLE" in
#   analyst)      AGENT=gemini;  PERM=--deny-all      ;;
_SH_CASE = re.compile(r'case\s+"\$ROLE"\s+in(?P<body>.*?)\besac\b', re.S)
_SH_ROLE = re.compile(r"^\s*(?P<role>[a-z][a-z0-9-]*)\)\s*AGENT=(?P<backend>[A-Za-z0-9_-]+)\s*;")


def _module_literal(path: Path, name: str):
    """Giá trị literal của phép gán cấp module `name = ...` (có hoặc không chú thích kiểu)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return ast.literal_eval(node.value)
        elif isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return ast.literal_eval(node.value)
    raise LookupError(f"không thấy phép gán cấp module '{name} = ...'")


def _load_routing(root: Path, bad: list[str]) -> dict[str, list[str]]:
    doc = yaml.safe_load((root / ROUTING).read_text(encoding="utf-8")) or {}
    routing: dict[str, list[str]] = {}
    for dc, spec in (doc.get("dataClasses") or {}).items():
        backends = (spec or {}).get("allowedBackends")
        if not isinstance(backends, list):
            bad.append(f"{ROUTING}: dataClasses.{dc}.allowedBackends thiếu hoặc không phải danh sách")
            continue
        routing[str(dc)] = [str(b) for b in backends]
    if not routing:
        bad.append(f"{ROUTING}: không có dataClasses nào — không có gì để đối chiếu")
    return routing


def _check_profiles(root: Path, routing: dict[str, list[str]], bad: list[str]) -> int:
    checked = 0
    for path in sorted((root / "profiles").glob("*.yaml")):
        name = path.stem
        if name == "_schema":
            continue
        try:
            profile = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            bad.append(f"profiles/{path.name}: YAML hỏng — {exc}")
            continue
        checked += 1
        dc = profile.get("dataClass")
        if dc not in routing:
            bad.append(f"{name}: dataClass '{dc}' không có trong {ROUTING} "
                       f"(có: {', '.join(routing)})")
            continue
        agents = profile.get("agents")
        if not isinstance(agents, dict) or not agents:
            bad.append(f"{name}: thiếu khối agents — không biết hồ sơ chạy trên backend nào")
            continue
        for slot, backend in agents.items():
            if backend not in routing[dc]:
                bad.append(f"{name}: agents.{slot} = '{backend}' không được phép với dataClass "
                           f"'{dc}' (chỉ cho phép: {', '.join(routing[dc]) or '(không backend nào)'})")
    return checked


def _compare(label: str, table: dict, routing: dict[str, list[str]], bad: list[str]) -> None:
    for dc in sorted(set(routing) | set(table)):
        if dc not in table:
            bad.append(f"{label}: thiếu mức '{dc}' mà {ROUTING} có")
        elif dc not in routing:
            bad.append(f"{label}: có mức '{dc}' mà {ROUTING} không khai")
        else:
            extra = sorted(set(table[dc]) - set(routing[dc]))
            missing = sorted(set(routing[dc]) - set(table[dc]))
            if extra or missing:
                bad.append(f"{label}['{dc}'] lệch {ROUTING}: thừa {extra}, thiếu {missing}")


def _rego_allowed_backends(path: Path) -> dict[str, list[str]]:
    block = _REGO_BLOCK.search(path.read_text(encoding="utf-8"))
    entries = {
        m["dc"]: _QUOTED.findall(m["items"]) for m in _REGO_ENTRY.finditer(block["body"])
    } if block else {}
    if not entries:
        raise LookupError("không đọc được khối `allowed_backends := {...}`")
    return entries


def _run_role_backends(path: Path) -> dict[str, str]:
    case = _SH_CASE.search(path.read_text(encoding="utf-8"))
    table = {
        m["role"]: m["backend"]
        for line in (case["body"].splitlines() if case else [])
        if (m := _SH_ROLE.match(line))
    }
    if not table:
        raise LookupError('không đọc được bảng `case "$ROLE" in ... esac`')
    return table


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                    help="gốc repo (mặc định: thư mục cha của scripts/)")
    root = ap.parse_args(argv).root

    bad: list[str] = []
    routing = _load_routing(root, bad)
    profiles = _check_profiles(root, routing, bad)

    try:
        _compare(f"MODEL_POLICY ({POLICIES_PY})",
                 _module_literal(root / POLICIES_PY, "MODEL_POLICY"), routing, bad)
    except (OSError, SyntaxError, ValueError, LookupError) as exc:
        bad.append(f"{POLICIES_PY}: không đọc được MODEL_POLICY — {exc}")

    try:
        _compare(f"allowed_backends ({FLEET_REGO})",
                 _rego_allowed_backends(root / FLEET_REGO), routing, bad)
    except (OSError, LookupError) as exc:
        bad.append(f"{FLEET_REGO}: {exc}")

    roles = 0
    try:
        py = {role: spec[0] for role, spec in
              _module_literal(root / ACPX_CLIENT_PY, "ROLE_BACKENDS").items()}
        sh = _run_role_backends(root / RUN_ROLE_SH)
        roles = len(py)
        for role in sorted(set(py) | set(sh)):
            if role not in py:
                bad.append(f"vai trò '{role}' có trong {RUN_ROLE_SH} ({sh[role]}) "
                           f"nhưng thiếu trong ROLE_BACKENDS")
            elif role not in sh:
                bad.append(f"vai trò '{role}' có trong ROLE_BACKENDS ({py[role]}) "
                           f"nhưng thiếu trong {RUN_ROLE_SH}")
            elif py[role] != sh[role]:
                bad.append(f"vai trò '{role}': ROLE_BACKENDS nói '{py[role]}' nhưng run-role.sh "
                           f"chạy '{sh[role]}' — chốt dataClass sẽ kiểm sai backend")
    except (OSError, SyntaxError, ValueError, LookupError, TypeError, IndexError) as exc:
        bad.append(f"không đối chiếu được backend theo vai trò ({ACPX_CLIENT_PY} ↔ "
                   f"{RUN_ROLE_SH}) — {exc}")

    if bad:
        print("\n".join(f"  {b}" for b in bad))
        return 1
    print(f"{profiles} hồ sơ, {len(routing)} mức dữ liệu, {roles} vai trò")
    return 0


if __name__ == "__main__":
    sys.exit(main())
