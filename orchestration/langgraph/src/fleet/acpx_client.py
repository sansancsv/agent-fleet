"""
Cầu nối LangGraph → acpx.

Vì sao không gọi thẳng API model trong LangGraph?
    Vì các agent lập trình (Claude Code, Codex, Gemini CLI) không phải là "một
    lần gọi model". Chúng có vòng lặp công cụ riêng, có quyền đọc/ghi file, có
    phiên trạng thái. acpx chuẩn hoá tất cả sau một giao diện duy nhất (ACP),
    nên LangGraph chỉ cần biết: "chạy vai trò X với prompt Y trong thư mục Z".

Nhờ vậy đổi backend (Claude ↔ Codex ↔ model tự host) là đổi một dòng cấu hình,
không phải viết lại đồ thị.

Hai chế độ chạy, chọn bằng biến môi trường:
    AGENT_RUNNER_URL đặt   → gọi HTTP tới dịch vụ agent-runner (compose/K8s).
                             Mọi lượt agent của cả fleet đi qua một chỗ.
    AGENT_RUNNER_URL trống → spawn acpx ngay trong tiến trình này (dev, test).
Cả hai đều truyền prompt bằng argv/JSON — không có shell nào diễn giải nó.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import time
import urllib.error
import urllib.request
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


# Backend acpx -> tiền tố biến môi trường chứa khoá của nhà cung cấp đó.
# Dùng để THU HẸP khoá: một lượt chạy `claude` không có lý do gì được nhìn thấy
# khoá OpenAI và Gemini — giảm bán kính thiệt hại nếu lượt đó bị chèn lệnh.
BACKEND_PROVIDER: dict[str, str] = {
    "claude": "ANTHROPIC",
    "codex": "OPENAI",
    "gemini": "GEMINI",
}


@dataclass(slots=True)
class AgentResult:
    role: str
    text: str
    exit_code: int
    status: dict[str, str] = field(default_factory=dict)
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    @property
    def outcome(self) -> str:
        return self.status.get("outcome", "success" if self.ok else "blocked")


class AcpxError(RuntimeError):
    pass


def provider_env(backend: str, base: dict[str, str] | None = None) -> dict[str, str]:
    """Môi trường cho một lượt acpx, đã GỠ khoá của các nhà cung cấp khác.

    Vì sao cần: acpx truyền môi trường của nó xuống mọi tiến trình con, kể cả
    lệnh shell mà chính agent quyết định chạy. Nghĩa là một lượt `implementer`
    (có quyền exec) nhìn thấy được mọi khoá model có trong container. Không gỡ
    được khoá của backend đang dùng — acpx cần nó để gọi model — nhưng gỡ được
    hai khoá còn lại, tức là hạ bán kính thiệt hại từ ba nhà cung cấp xuống một.

    Backend lạ (chưa có trong BACKEND_PROVIDER) → gỡ TẤT CẢ khoá đã biết. Fail
    closed: thà lượt đó hỏng vì thiếu khoá còn hơn lặng lẽ phơi cả ba.

    Bản sao của logic này nằm ở `execution-plane/scripts/run-role.sh` (nhánh
    chạy qua agent-runner). Hai chỗ phải khớp nhau; `scripts/validate.sh` bước
    5d kiểm điều đó.
    """
    env = dict(base if base is not None else os.environ)
    keep = BACKEND_PROVIDER.get(backend)
    for provider in set(BACKEND_PROVIDER.values()):
        if provider == keep:
            continue
        env.pop(f"ACPX_AUTH_{provider}_API_KEY", None)
        env.pop(f"{provider}_API_KEY", None)
    return env


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

    started = time.monotonic()

    runner_url = os.environ.get("AGENT_RUNNER_URL", "").rstrip("/")
    if runner_url:
        if session:
            raise AcpxError("Phiên có trạng thái chưa được hỗ trợ qua agent-runner API")
        return await asyncio.to_thread(
            _run_remote, runner_url, role, prompt, cwd, perm == "approve-all", timeout_s
        )

    # THỨ TỰ THAM SỐ (đối chiếu acpx 0.13.2): --cwd/--format/--json-strict/
    # --suppress-reads/--{perm} là tuỳ chọn TOÀN CỤC của `acpx`, phải đứng
    # TRƯỚC tên backend. Đặt sau "backend exec/-s" bị từ chối
    # "unknown option '--cwd'" — xem chú thích trong run-role.sh (nguồn sự thật
    # cho hình dạng lệnh này; nhánh này chỉ dùng khi AGENT_RUNNER_URL trống).
    argv: list[str] = [
        "acpx", "--cwd", cwd, f"--{perm}", "--format", "json", "--json-strict", "--suppress-reads",
    ]
    argv.append(backend)
    if session:
        # Phiên có trạng thái: agent nhớ ngữ cảnh repo giữa các lượt.
        argv += ["-s", session, prompt]
    else:
        argv += ["exec", prompt]

    env = {**provider_env(backend), "ACPX_NON_INTERACTIVE": "1"}

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
        duration_ms=int((time.monotonic() - started) * 1000),
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


def _run_remote(
    base_url: str, role: str, prompt: str, cwd: str, write: bool, timeout_s: int
) -> AgentResult:
    """Gọi POST /run của agent-runner. Chạy trong thread vì urllib chặn."""
    token = os.environ.get("AGENT_RUNNER_TOKEN", "")
    if not token:
        raise AcpxError("AGENT_RUNNER_TOKEN chưa đặt — không gọi được agent-runner")

    body = json.dumps(
        {"role": role, "cwd": cwd, "prompt": prompt, "write": write, "timeoutS": timeout_s},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/run",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        # +30s: runner tự cắt ở timeout_s và trả 504; ta chỉ là lớp bảo hiểm.
        with urllib.request.urlopen(req, timeout=timeout_s + 30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:800]
        raise AcpxError(f"{role}: agent-runner trả {exc.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AcpxError(f"{role}: không gọi được agent-runner tại {base_url}: {exc}") from None

    text = str(payload.get("text", ""))
    return AgentResult(
        role=role,
        text=text,
        exit_code=int(payload.get("exit", 0) or 0),
        status=payload.get("status") or _extract_status(text),
        # Runner đã đo sẵn (handleRun trong server.mjs). Lấy số của nó thay vì
        # đo lại ở đây: số của runner không tính thời gian đi trên mạng nội bộ.
        duration_ms=int(payload.get("durationMs", 0) or 0),
    )


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
