"""
=============================================================================
VẾT CHẠY (trajectory) — ghi lại agent đã làm gì, để còn cải tiến được
-----------------------------------------------------------------------------
Không ghi lại được vết chạy của agent thì không thể biết nó hỏng ở đâu, và
cũng không thể cải tiến bộ khung một cách có căn cứ.

Repo này đã có audit của gateway (ai gọi tool gì) và `permission.decision` của
LangGraph (ai duyệt cái gì). Cả hai trả lời câu hỏi KIỂM TOÁN. Không cái nào
trả lời được câu hỏi KỸ THUẬT: "quy trình thường hỏng ở nút nào", "sửa lại mấy
vòng thì thường bỏ cuộc", "thêm ràng buộc vào AGENTS.md xong thì lỗi đó còn
lặp lại không". Vết chạy trả lời nhóm câu hỏi thứ hai.

Định dạng: NDJSON, một dòng một sự kiện, một file một ngày. Cố ý không dùng
CSDL: file phẳng đọc được bằng `jq`, `grep`, pandas, và không thêm một dịch vụ
phải vận hành. Chỉ đổi sang CSDL khi truy vấn phẳng không còn đủ.

MỌI THỨ Ở ĐÂY ĐỀU FAIL-SOFT. Ghi vết chạy hỏng không được phép làm hỏng một
lượt giao hàng tính năng. Xem `_append()`.

Đọc số liệu:  python -m fleet.metrics       (hoặc `make metrics`)
=============================================================================
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

TRAJECTORY_DIR = Path(os.environ.get("FLEET_TRAJECTORY_DIR", "/var/log/fleet/trajectory"))

# Một bản ghi lớn hơn thế là ai đó đang nhét cả transcript vào đây. Transcript
# đã nằm trong $FLEET_LOG_DIR/<role>/<session>.ndjson rồi — ở đây chỉ giữ số
# đo và tham chiếu. Đúng tinh thần compaction: lưu đường dẫn, không lưu nội dung.
MAX_RECORD_BYTES = 8192


def _append(record: dict[str, Any]) -> None:
    """Ghi một dòng NDJSON + in ra stdout cho hệ thống gom log.

    Nuốt mọi lỗi I/O có chủ đích: quan sát là thứ hỗ trợ, không phải thứ quy
    trình phụ thuộc vào. Volume chưa mount thì mất số liệu, không mất công việc.
    """
    line = json.dumps(record, ensure_ascii=False)
    if len(line.encode("utf-8")) > MAX_RECORD_BYTES:
        record = {**record, "truncated": True}
        record.pop("note", None)
        line = json.dumps(record, ensure_ascii=False)

    # stdout luôn có, kể cả khi volume hỏng.
    print(line, file=sys.stdout, flush=True)

    try:
        TRAJECTORY_DIR.mkdir(parents=True, exist_ok=True)
        day = record.get("ts", "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with (TRAJECTORY_DIR / f"{day}.ndjson").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# GHI — ba loại sự kiện, cố ý không nhiều hơn
# ---------------------------------------------------------------------------
def run_started(task_id: str, *, repo: str = "", profile: str = "", title: str = "") -> None:
    _append({"ts": _now(), "event": "run.start", "task_id": task_id,
             "repo": repo, "profile": profile, "title": title[:200]})


def step(
    task_id: str,
    node: str,
    *,
    role: str = "",
    outcome: str = "",
    duration_ms: int = 0,
    output_chars: int = 0,
    revision_count: int = 0,
    risk: str = "",
    blockers: list[str] | None = None,
    note: str = "",
) -> None:
    """Một nút của đồ thị đã chạy xong.

    `blockers` là danh sách CHỮ KÝ phát hiện (`SEVERITY|file`), không phải nội
    dung phát hiện: đủ để đếm lỗi lặp lại, không đủ để rò nội dung mã nguồn ra
    hệ thống log.
    """
    _append({
        "ts": _now(), "event": "step", "task_id": task_id, "node": node,
        "role": role, "outcome": outcome, "duration_ms": duration_ms,
        "output_chars": output_chars, "revision_count": revision_count,
        "risk": risk, "blockers": (blockers or [])[:20],
        **({"note": note[:500]} if note else {}),
    })


def run_finished(
    task_id: str,
    *,
    outcome: str,
    duration_s: float,
    repo: str = "",
    approved_by: str = "",
    revision_count: int = 0,
    escalated: bool = False,
    pr_url: str = "",
) -> None:
    _append({"ts": _now(), "event": "run.end", "task_id": task_id, "repo": repo,
             "outcome": outcome, "duration_s": round(duration_s, 1),
             "approved_by": approved_by, "revision_count": revision_count,
             "escalated": escalated, "pr_url": pr_url})


def approval(task_id: str, *, by: str, approved: bool, profile: str = "") -> None:
    _append({"ts": _now(), "event": "approval", "task_id": task_id,
             "by": by, "approved": approved, "profile": profile})


def permission_denied(task_id: str, *, profile: str, by: str, reason: str) -> None:
    """Một yêu cầu bị server.py chặn TRƯỚC KHI chạm graph hay agent nào.

    Ba nơi gọi:
      * /runs/<id>/resume — `by` không nằm trong approvers. `human_approval`
        trong graph.py chỉ chạy sau khi server.py đã cho `by` qua kiểm, nên
        một yêu cầu bị 403 không bao giờ tới đó. Hàm này tách khỏi
        `approval()` (vốn chỉ ghi quyết định của một approver hợp lệ, dù
        approved=True hay False).
      * /profiles/<tên>/run — người gửi không thuộc requesters, hoặc chốt
        dataClass từ chối backend (`reason` = "backend-not-allowed:<backend>");
        `by` là người gửi yêu cầu.
      * /runs/wait — chốt dataClass từ chối một hay nhiều backend của đồ thị
        (`reason` = "backend-not-allowed:<backend>[,<backend>...]"), trước khi
        có thread; `task_id` là thread_id, `by` là `requester` trong input.
    Không gọi hàm này thì các lượt bị từ chối không để lại dấu vết bền nào.
    """
    _append({"ts": _now(), "event": "permission.denied", "task_id": task_id,
             "profile": profile, "by": by, "reason": reason})


# ---------------------------------------------------------------------------
# ĐỌC — dùng bởi fleet.metrics
# ---------------------------------------------------------------------------
def read_all(directory: Path | None = None) -> Iterator[dict[str, Any]]:
    """Đọc mọi bản ghi, bỏ qua dòng hỏng.

    Dòng hỏng xảy ra thật khi tiến trình bị giết giữa lúc ghi. Một dòng cụt
    không được phép làm hỏng cả báo cáo.
    """
    root = directory or TRAJECTORY_DIR
    if not root.is_dir():
        return
    for path in sorted(root.glob("*.ndjson")):
        try:
            with path.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue


def finding_signature(severity: str, location: str) -> str:
    """Chữ ký của một phát hiện: mức + TÊN FILE (bỏ số dòng).

    Bỏ số dòng có chủ đích: cùng một lỗi sau khi code dịch đi vài dòng vẫn phải
    được đếm là lỗi lặp lại, nếu không chỉ số "lỗi lặp lại" sẽ luôn đẹp một
    cách giả tạo.
    """
    return f"{severity}|{str(location).split(':', 1)[0]}"
