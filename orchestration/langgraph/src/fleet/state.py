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
import time
from typing import Annotated, Literal, NotRequired, TypedDict

Risk = Literal["trivial", "standard", "risky"]
Outcome = Literal["success", "partial", "blocked", "rejected"]


class Finding(TypedDict):
    role: str
    severity: str          # BLOCKER | MAJOR | MINOR | NIT | CRITICAL
    location: str          # file:dòng
    detail: str
    round: NotRequired[int]  # vòng thẩm định đã nêu nó (= revision_count); thiếu = vòng 0


class ReviewRun(TypedDict):
    """Một lượt thẩm định có HOÀN TẤT không — không phải nội dung phát hiện.

    "Thẩm định sạch" và "thẩm định không chạy" (runner bận, timeout, thiếu khoá,
    không có khối fleet-status...) đều cho ra danh sách phát hiện RỖNG. Chỉ bản
    ghi này phân biệt được hai trường hợp đó; `gate()` đọc nó trước mọi thứ khác.
    """
    role: str
    round: int             # = revision_count lúc thẩm định
    ok: bool
    reason: str            # vì sao không hoàn tất; rỗng khi ok


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
    base_ref: str          # nhánh gốc đã dùng để tạo worktree (origin/main, origin/master...)
    risk: Risk

    # Mốc bắt đầu (epoch giây). Dùng để tính "phiên dài" trong fleet.metrics —
    # phải nằm trong state chứ không phải biến cục bộ, vì quy trình có thể ngủ
    # hàng ngày ở điểm chờ duyệt rồi mới chạy tiếp trong một tiến trình khác.
    started_at: float

    # `operator.add` = các nút chạy song song được phép cùng ghi thêm vào danh sách
    # mà không giẫm lên nhau. Đây là lý do dùng Annotated thay vì list thường.
    transcripts: Annotated[list[dict], operator.add]
    findings: Annotated[list[Finding], operator.add]
    reviews: Annotated[list[ReviewRun], operator.add]

    # --- Kết luận của lượt hiện thực gần nhất --------------------------------
    # Nút `implement` ghi (có gọi git); cạnh điều kiện sau nó chỉ ĐỌC, nên vẫn
    # là hàm thuần tuý. Rỗng = đi tiếp tới thẩm định.
    implement_problem: str
    implement_question: str  # câu hỏi của implementer — đưa vào summary khi leo thang

    # --- Điều khiển vòng lặp -------------------------------------------------
    revision_count: int    # đã sửa lại mấy lần — chặn lặp vô hạn
    max_revisions: int

    # --- Người tham gia ------------------------------------------------------
    approved_by: str
    approval_note: str

    # --- Kết quả -------------------------------------------------------------
    escalated: bool        # tự động hoá hết cách → chuyển cho người (xem graph.escalate)
    outcome: Outcome
    pr_url: str
    summary: str


def initial_state(**kwargs) -> FleetState:
    base: FleetState = {
        "profile": "engineering",
        "transcripts": [],
        "findings": [],
        "reviews": [],
        "revision_count": 0,
        "max_revisions": 2,
        "outcome": "partial",
        "started_at": time.time(),
    }
    base.update(kwargs)  # type: ignore[typeddict-item]
    return base


def current_findings(state: FleetState) -> list[Finding]:
    """Phát hiện của vòng thẩm định HIỆN TẠI.

    `findings` cộng dồn qua mọi vòng (operator.add). Mục đã sửa ở vòng trước vẫn
    nằm đó; đọc cả danh sách thì một mục đã sửa xong vẫn chặn mãi, và vòng sửa
    lại không bao giờ tới được chờ duyệt.
    """
    rnd = state.get("revision_count", 0)
    return [f for f in state.get("findings", []) if f.get("round", 0) == rnd]


def blockers(state: FleetState) -> list[Finding]:
    return [f for f in current_findings(state) if f["severity"] in ("BLOCKER", "CRITICAL")]
