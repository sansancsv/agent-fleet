"""
Cầu nối LangGraph → acpx.

Vì sao không gọi thẳng API model trong LangGraph?
    Vì các agent lập trình (Claude Code, Codex, Gemini CLI) không phải là "một
    lần gọi model". Chúng có vòng lặp công cụ riêng, có quyền đọc/ghi file, có
    phiên trạng thái. acpx chuẩn hoá tất cả sau một giao diện duy nhất (ACP),
    nên LangGraph chỉ cần biết: "chạy vai trò X với prompt Y trong thư mục Z".

Nhờ vậy đổi backend (Claude ↔ Codex ↔ model tự host) là đổi một dòng cấu hình,
không phải viết lại đồ thị.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from dataclasses import dataclass, field
from typing import Any, Literal

Permission = Literal["approve-all", "approve-reads", "deny-all"]

# Ánh xạ vai trò -> (backend acpx, quyền mặc định).
# Cố ý để reviewer/security dùng backend khác implementer: cùng một model vừa
# viết vừa chấm sẽ bỏ sót cùng một loại lỗi.
ROLE_BACKENDS: dict[str, tuple[str, Permission]] = {
    "orchestrator": ("claude", "approve-reads"),
    "architect": ("claude", "approve-reads"),
    "implementer": ("claude", "approve-all"),
    "tester": ("claude", "approve-all"),
    "reviewer": ("codex", "deny-all"),
    "security": ("codex", "deny-all"),
    "docs-writer": ("gemini", "approve-reads"),
    "sre": ("claude", "approve-reads"),
    "analyst": ("gemini", "deny-all"),
}


@dataclass(slots=True)
class AgentResult:
    role: str
    text: str
    exit_code: int
    status: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    @property
    def outcome(self) -> str:
        return self.status.get("outcome", "success" if self.ok else "blocked")


class AcpxError(RuntimeError):
    pass


async def run_role(
    role: str,
    prompt: str,
    cwd: str,
    *,
    permission: Permission | None = None,
    session: str | None = None,
    timeout_s: int = 1800,
) -> AgentResult:
    """Chạy một vai trò một lượt và trả về kết quả đã phân tích.

    `--format json --json-strict` bảo đảm stdout chỉ chứa NDJSON các thông điệp
    ACP thô, mỗi dòng một thông điệp JSON-RPC — phân tích bằng máy, không regex.
    """
    if role not in ROLE_BACKENDS:
        raise AcpxError(f"Vai trò không hợp lệ: {role}")

    backend, default_perm = ROLE_BACKENDS[role]
    perm = permission or default_perm

    argv: list[str] = ["acpx", backend]
    if session:
        # Phiên có trạng thái: agent nhớ ngữ cảnh repo giữa các lượt.
        argv += ["-s", session, prompt]
    else:
        argv += ["exec", prompt]
    argv += ["--cwd", cwd, f"--{perm}", "--format", "json", "--json-strict", "--suppress-reads"]

    env = {**os.environ, "ACPX_NON_INTERACTIVE": "1"}

    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        raise AcpxError(f"{role} vượt quá {timeout_s}s: {shlex.join(argv)}") from None

    text = _extract_text(stdout.decode("utf-8", "replace"))
    if proc.returncode != 0 and not text:
        raise AcpxError(f"{role} thất bại (mã {proc.returncode}): {stderr.decode()[:800]}")

    return AgentResult(
        role=role,
        text=text,
        exit_code=proc.returncode or 0,
        status=_extract_status(text),
    )


async def fanout(
    roles: list[str],
    prompt: str,
    cwd: str,
    *,
    timeout_s: int = 1800,
) -> list[AgentResult]:
    """Chạy nhiều vai trò SONG SONG trên cùng một đầu vào.

    Dùng cho thẩm định chéo: ba model khác nhà cung cấp cùng soi một diff cho
    vùng phủ lỗi rộng hơn nhiều so với gọi một model ba lần.
    An toàn vì mọi vai trò trong nhóm này đều `deny-all` (chỉ đọc).
    """
    results = await asyncio.gather(
        *(run_role(r, prompt, cwd, timeout_s=timeout_s) for r in roles),
        return_exceptions=True,
    )
    out: list[AgentResult] = []
    for role, res in zip(roles, results, strict=True):
        if isinstance(res, BaseException):
            out.append(AgentResult(role=role, text=f"(lỗi: {res})", exit_code=1))
        else:
            out.append(res)
    return out


def _extract_text(ndjson: str) -> str:
    chunks: list[str] = []
    for line in ndjson.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg: Any = json.loads(line)
        except json.JSONDecodeError:
            continue
        update = (msg.get("params") or {}).get("update") or {}
        if update.get("sessionUpdate") == "agent_message_chunk":
            content = update.get("content") or {}
            if content.get("type") == "text":
                chunks.append(content.get("text", ""))
    return "".join(chunks)


def _extract_status(text: str) -> dict[str, str]:
    """Đọc khối ```fleet-status``` mà hiến chương fleet bắt mọi agent phải trả về."""
    marker = "```fleet-status"
    if marker not in text:
        return {}
    block = text.split(marker, 1)[1].split("```", 1)[0]
    status: dict[str, str] = {}
    for row in block.splitlines():
        if ":" in row:
            key, _, value = row.partition(":")
            status[key.strip()] = value.strip()
    return status
