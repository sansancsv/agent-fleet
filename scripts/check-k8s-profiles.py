#!/usr/bin/env python3
"""Bắt lỗi "langgraph trên Kubernetes không thấy hồ sơ phòng ban".

VÌ SAO CÓ PHÉP KIỂM NÀY: server.py đọc `profiles/*.yaml` từ FLEET_PROFILES_DIR
ở MỖI yêu cầu — mọi endpoint /profiles/<tên>/..., và danh sách `approvers` khi
/runs/<id>/resume. Compose bind-mount `../../profiles` vào đó. Bản đầu của
`deploy/k8s/70-langgraph.yaml` thì không mount gì, nên trên K8s mọi endpoint
theo hồ sơ trả 404: hỏng theo hướng an toàn nhưng fleet không dùng được. Và
không gì báo lỗi lúc apply — pod vẫn Ready, /ok vẫn 200, chỉ có `profiles: []`.

Phép kiểm, trên container `langgraph` của Deployment `langgraph`:
  * FLEET_PROFILES_DIR được đặt tường minh bằng `value:` — không dựa vào mặc
    định trong server.py, giống compose;
  * có volumeMount đúng đường dẫn đó, `readOnly: true`, KHÔNG subPath: mount
    bằng subPath thì kubelet không cập nhật file khi ConfigMap đổi;
  * volume là configMap (sinh từ profiles/, lệnh ở docs/01-cai-dat.md §B),
    KHÔNG `optional: true` (thiếu ConfigMap thì pod chạy với thư mục rỗng —
    lại 404 im lặng) và KHÔNG `items` (hồ sơ mới thêm vào profiles/ sẽ không
    tới được pod).

Không kiểm ConfigMap có tồn tại hay không: nó được sinh từ git bằng kubectl,
không nằm trong deploy/k8s/. Thiếu nó thì pod kẹt ở ContainerCreating — một
lỗi ồn ào, không phải loại lỗi im lặng mà phép kiểm này phòng.

Thành công: in một dòng tóm tắt, thoát 0.
Thất bại:   in từng lỗi (thụt hai dấu cách), thoát 1.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

DEPLOYMENT = "langgraph"
CONTAINER = "langgraph"
ENV = "FLEET_PROFILES_DIR"


def check_container(where: str, c: dict, volumes: dict, problems: list[str]) -> str:
    """Kiểm một container; trả dòng tóm tắt nếu đạt, chuỗi rỗng nếu không."""
    env = {e.get("name"): e.get("value") for e in c.get("env") or []}
    pdir = env.get(ENV)
    if not pdir:
        problems.append(f"{where}: không đặt {ENV} bằng `value:` — đặt tường minh "
                        f"/fleet/profiles như compose, đừng dựa vào mặc định trong server.py")
        return ""

    mounts = [m for m in c.get("volumeMounts") or []
              if os.path.normpath(m.get("mountPath") or "") == os.path.normpath(pdir)]
    if not mounts:
        problems.append(f"{where}: không có volumeMount nào tại {ENV}={pdir} "
                        f"→ mọi endpoint theo hồ sơ trả 404")
        return ""

    before = len(problems)
    m = mounts[0]
    if m.get("readOnly") is not True:
        problems.append(f"{where}: mount {pdir} phải có readOnly: true (compose mount :ro)")
    if m.get("subPath") or m.get("subPathExpr"):
        problems.append(f"{where}: mount {pdir} dùng subPath — kubelet không cập nhật file "
                        f"khi ConfigMap đổi, hồ sơ sửa xong không tới được pod")

    cm = (volumes.get(m.get("name")) or {}).get("configMap")
    if not cm:
        problems.append(f"{where}: volume '{m.get('name')}' tại {pdir} không phải configMap "
                        f"sinh từ profiles/")
        return ""
    if cm.get("optional"):
        problems.append(f"{where}: configMap '{cm.get('name')}' đặt optional: true — thiếu "
                        f"ConfigMap thì pod chạy với thư mục rỗng và trả 404 im lặng")
    if cm.get("items"):
        problems.append(f"{where}: configMap '{cm.get('name')}' dùng items — hồ sơ mới thêm "
                        f"vào profiles/ sẽ không xuất hiện trong pod")

    if len(problems) > before:
        return ""
    return f"{ENV}={pdir} ← configMap {cm.get('name')} (chỉ đọc, cả thư mục)"


def main(k8s_dir: str) -> int:
    problems: list[str] = []
    found: list[tuple[Path, dict]] = []
    for path in sorted(Path(k8s_dir).glob("*.yaml")):
        try:
            docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError as exc:
            problems.append(f"{path}: YAML hỏng — {exc}")
            continue
        found += [
            (path, d) for d in docs
            if isinstance(d, dict) and d.get("kind") == "Deployment"
            and (d.get("metadata") or {}).get("name") == DEPLOYMENT
        ]

    if not found and not problems:
        problems.append(f"không thấy Deployment '{DEPLOYMENT}' trong {k8s_dir}/")

    summaries: list[str] = []
    for path, d in found:
        spec = ((d.get("spec") or {}).get("template") or {}).get("spec") or {}
        volumes = {v.get("name"): v for v in spec.get("volumes") or []}
        containers = [c for c in spec.get("containers") or [] if c.get("name") == CONTAINER]
        if not containers:
            problems.append(f"{path}: Deployment '{DEPLOYMENT}' không có container '{CONTAINER}'")
        for c in containers:
            line = check_container(f"{path}: {DEPLOYMENT}", c, volumes, problems)
            if line:
                summaries.append(line)

    if problems:
        for p in problems:
            print(f"  {p}")
        return 1
    print("; ".join(summaries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "deploy/k8s"))
