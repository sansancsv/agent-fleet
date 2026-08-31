"""Trạng thái chia sẻ giữa các nút của đồ thị.

Nguyên tắc: trạng thái phải **tuần tự hoá được** (serializable) hoàn toàn, vì
LangGraph ghi nó xuống checkpointer (PostgreSQL) sau mỗi bước. Nhờ đó:

  * quy trình sống sót qua việc pod bị giết giữa chừng;
  * dừng chờ người duyệt hàng giờ mà không giữ tiến trình nào;
  * tái hiện lại đúng nhánh đã đi khi điều tra sự cố.

Đừng nhét đối tượng kết nối, file handle hay coroutine vào đây.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

Risk = Literal["trivial", "standard", "risky"]
Outcome = Literal["success", "partial", "blocked", "rejected"]


class Finding(TypedDict):
    role: str
    severity: str          # BLOCKER | MAJOR | MINOR | NIT | CRITICAL
    location: str          # file:dòng
    detail: str


class FleetState(TypedDict, total=False):
    # --- Đầu vào -------------------------------------------------------------
    task_id: str
    title: str
    repo: str
    profile: str           # tên hồ sơ phòng ban, mặc định "engineering"
    requester: str

    # --- Do đồ thị sinh ra ---------------------------------------------------
    worktree: str
    branch: str
    risk: Risk

    # `operator.add` = các nút chạy song song được phép cùng ghi thêm vào danh sách
    # mà không giẫm lên nhau. Đây là lý do dùng Annotated thay vì list thường.
    transcripts: Annotated[list[dict], operator.add]
    findings: Annotated[list[Finding], operator.add]

    # --- Điều khiển vòng lặp -------------------------------------------------
    revision_count: int    # đã sửa lại mấy lần — chặn lặp vô hạn
    max_revisions: int

    # --- Người tham gia ------------------------------------------------------
    approved_by: str
    approval_note: str

    # --- Kết quả -------------------------------------------------------------
    outcome: Outcome
    pr_url: str
    summary: str


def initial_state(**kwargs) -> FleetState:
    base: FleetState = {
        "profile": "engineering",
        "transcripts": [],
        "findings": [],
        "revision_count": 0,
        "max_revisions": 2,
        "outcome": "partial",
    }
    base.update(kwargs)  # type: ignore[typeddict-item]
    return base


def blockers(state: FleetState) -> list[Finding]:
    return [f for f in state.get("findings", []) if f["severity"] in ("BLOCKER", "CRITICAL")]
