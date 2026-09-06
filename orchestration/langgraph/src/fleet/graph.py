"""
=============================================================================
ĐỒ THỊ ĐIỀU PHỐI FLEET (LangGraph)
-----------------------------------------------------------------------------
Chọn LangGraph cho tầng nào?

    n8n        → quy trình NGHIỆP VỤ, do phòng ban sở hữu, kéo-thả, nhiều tích hợp
    acpx flow  → quy trình TRONG REPO, versioned cùng code, dev sở hữu
    LangGraph  → quy trình DÀI, BỀN VỮNG, có người duyệt giữa chừng, cần
                 tái hiện chính xác và chạy lại từ điểm dừng  ← file này

Ba năng lực khiến LangGraph xứng đáng có mặt trong kiến trúc:
  1. `checkpointer` — trạng thái ghi xuống PostgreSQL sau MỖI bước. Pod chết,
     quy trình vẫn tiếp tục đúng chỗ đã dừng.
  2. `interrupt()`  — dừng chờ người thật, hàng giờ hoặc hàng ngày, không giữ
     tiến trình nào. Đây là thứ biến "demo agent" thành "hệ thống doanh nghiệp".
  3. Nhánh song song với quy tắc gộp trạng thái tường minh (`operator.add`).

Chạy thử:      langgraph dev
Đóng gói:      langgraph build -t fleet-orchestrator:latest
=============================================================================
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from typing import Literal

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from . import memory, trajectory
from .acpx_client import AgentResult, fanout, run_role
from .policies import parse_findings, risk_from_text
from .state import FleetState, blockers, initial_state

REPO_ROOT = os.environ.get("FLEET_REPO_ROOT", "/srv/repos")

# LangGraph chạy bằng root (mount /root/.acpx trong compose/K8s giả định vậy),
# nhưng lượt agent thật (implementer, tester...) chạy qua dịch vụ agent-runner
# bằng user `node`. `git worktree add` bên dưới tạo thư mục MỚI, và nó thuộc
# sở hữu của tiến trình gọi nó — tức root. Không chown lại, implementer nhận
# EACCES ngay khi mở file để ghi, lặng lẽ không viết được dòng code nào, và
# graph vẫn đi tiếp qua review/gate như thể mọi việc suôn sẻ (diff rỗng không
# có gì để reviewer chặn). Đã thấy lỗi này thật khi chạy demo-flow lần đầu.
#
# CHOWN TOÀN BỘ REPO GỐC, KHÔNG CHỈ WORKTREE: `git fetch` và `git worktree add`
# rải file root-owned ra NHIỀU chỗ khác nhau bên trong `<repo>/.git` — đã thấy
# thật cả tám: packed-refs, config, FETCH_HEAD, refs/heads/feat/<task-id> (và
# thư mục cha refs/heads/feat/ vì tên nhánh có dấu "/"), logs/refs/heads/feat/
# tương ứng, và thư mục quản trị worktrees/<tên>. Ban đầu tưởng chỉ cần chown
# worktrees/<tên> (đủ để tạo index.lock), nhưng commit vào NHÁNH MỚI còn cần
# ghi refs/heads/... trong repo gốc — chown lẻ từng đường dẫn là trò đuổi bắt
# vô tận. `repo` là kho do fleet quản lý riêng cho việc này nên chown đệ quy
# toàn bộ là an toàn.
WORKTREE_OWNER_UID = int(os.environ.get("FLEET_WORKTREE_UID", "1000"))
WORKTREE_OWNER_GID = int(os.environ.get("FLEET_WORKTREE_GID", "1000"))


# ---------------------------------------------------------------------------
# BỘ NHỚ VÀ VẾT CHẠY — hai móc dùng chung cho mọi nút có gọi model
# ---------------------------------------------------------------------------
def _memory_prefix(state: FleetState) -> str:
    """Ghi chú của các lượt trước, nạp vào đầu prompt.

    Trả về "" khi chưa có gì — không nạp khối rỗng chỉ để cho có. Nội dung đã
    được `memory.context_block` bọc trong thẻ và ghi rõ là dữ liệu tham khảo.
    """
    return memory.context_block(state.get("repo", ""), state.get("task_id", ""))


def _after_turn(
    state: FleetState,
    node: str,
    res: AgentResult,
    *,
    blocker_sigs: list[str] | None = None,
) -> None:
    """Chạy sau MỖI lượt agent: ghi tiến độ, ghi vết chạy, thu bài học.

    Đây là chỗ vòng lặp Hashimoto khép lại. Agent chỉ *nêu* bài học qua trường
    `lesson:` trong khối fleet-status; hàm này *quyết định* có ghi hay không.
    Nếu để agent tự ghi file bộ nhớ thì (a) mất tính xác định, (b) bộ nhớ thành
    nơi agent tự cấp thêm chỉ dẫn cho chính mình ở lượt sau.

    Hàm này không bao giờ được ném lỗi: quan sát hỏng không làm hỏng công việc.
    """
    task_id = state.get("task_id", "")
    note = f"{res.outcome}"
    if res.status.get("confidence"):
        note += f" (tin cậy {res.status['confidence']})"

    memory.append_step(task_id, node, note)
    trajectory.step(
        task_id,
        node,
        role=res.role,
        outcome=res.outcome,
        duration_ms=res.duration_ms,
        output_chars=len(res.text),
        revision_count=state.get("revision_count", 0),
        risk=state.get("risk", ""),
        blockers=blocker_sigs,
    )

    lesson = res.status.get("lesson", "")
    if lesson and memory.record_lesson(state.get("repo", ""), lesson, task_id=task_id):
        trajectory.step(task_id, f"{node}:lesson", role=res.role, outcome="recorded",
                        note=lesson)


# ---------------------------------------------------------------------------
# NÚT 1 — Chuẩn bị. Xác định thuần tuý, không có model tham gia.
# ---------------------------------------------------------------------------
async def prepare(state: FleetState) -> dict:
    task_id = state["task_id"].lower()
    repo = state["repo"]
    branch = f"feat/{task_id}"
    worktree = f"{REPO_ROOT}/wt-{task_id}"

    subprocess.run(["git", "-C", repo, "fetch", "--prune", "origin"], check=True)
    subprocess.run(
        ["git", "-C", repo, "worktree", "add", "-B", branch, worktree, "origin/main"],
        check=True,
    )
    # Giao lại quyền sở hữu cho user thật sự sẽ ghi — cả worktree lẫn repo gốc
    # (fetch + worktree add rải file root-owned khắp .git, xem chú thích trên).
    owner = f"{WORKTREE_OWNER_UID}:{WORKTREE_OWNER_GID}"
    subprocess.run(["chown", "-R", owner, repo], check=True)
    subprocess.run(["chown", "-R", owner, worktree], check=True)

    # Mở file tiến độ và ghi mốc bắt đầu. Tương ứng "initializer agent" trong
    # pattern long-running agent của Anthropic, nhưng làm bằng code — không tốn
    # một lượt model chỉ để viết header.
    memory.start_task(state["task_id"], state.get("title", ""), repo, branch)
    trajectory.run_started(state["task_id"], repo=repo, profile=state.get("profile", ""),
                           title=state.get("title", ""))

    return {
        "branch": branch,
        "worktree": worktree,
        # Ghi lại nếu bên gọi chưa đặt (ví dụ resume một thread cũ chưa có trường này).
        "started_at": state.get("started_at") or time.time(),
    }


# ---------------------------------------------------------------------------
# NÚT 2 — Phân loại rủi ro. Model phán đoán, nhưng đầu ra bị ép về tập hữu hạn.
# ---------------------------------------------------------------------------
async def triage(state: FleetState) -> dict:
    res = await run_role(
        "orchestrator",
        "Phân loại công việc sau vào ĐÚNG MỘT nhãn và chỉ in ra nhãn đó:\n"
        "trivial | standard | risky\n\n"
        f"Công việc: {state['title']}\n"
        "- trivial : sửa nhỏ, không đổi hành vi công khai\n"
        "- standard: tính năng thường, cần test\n"
        "- risky   : đổi lược đồ dữ liệu, đổi API công khai, đụng xác thực/thanh toán",
        cwd=state["worktree"],
        permission="deny-all",
    )
    _after_turn(state, "triage", res)
    return {"risk": risk_from_text(res.text), "transcripts": [{"node": "triage", "text": res.text}]}


# ---------------------------------------------------------------------------
# NÚT 3 — Thiết kế (chỉ nhánh risky).
# ---------------------------------------------------------------------------
async def design(state: FleetState) -> dict:
    res = await run_role(
        "architect",
        _memory_prefix(state)
        + f"Viết ADR cho {state['task_id']}: {state['title']}.\n"
        "Ghi vào docs/adr/ theo khuôn mẫu fleet-adr. Tối thiểu 2 phương án và "
        "phải nêu chi phí đảo ngược. KHÔNG viết code.",
        cwd=state["worktree"],
        permission="approve-all",
    )
    _after_turn(state, "design", res)
    return {"transcripts": [{"node": "design", "text": res.text}]}


# ---------------------------------------------------------------------------
# NÚT 4 — Hiện thực. Phi xác định: agent tự quyết cách làm.
# ---------------------------------------------------------------------------
async def implement(state: FleetState) -> dict:
    feedback = ""
    if state.get("revision_count", 0) > 0:
        items = "\n".join(
            f"- [{f['severity']}] {f['location']}: {f['detail']}" for f in blockers(state)
        )
        feedback = (
            "\n\nĐây là lượt sửa lại. CHỈ xử lý các mục dưới đây, không mở rộng phạm vi:\n"
            f"<untrusted source=\"review\">\n{items}\n</untrusted>"
        )

    res = await run_role(
        "implementer",
        _memory_prefix(state)
        + f"Hiện thực {state['task_id']}: {state['title']}\n\n"
        "Bắt buộc: đọc code trước khi sửa; thay đổi tối thiểu; chạy 'make test lint' "
        "cho tới khi xanh; commit theo Conventional Commits; KHÔNG push." + feedback,
        cwd=state["worktree"],
        permission="approve-all",
        timeout_s=2700,
    )
    _after_turn(state, "implement", res)
    return {
        "transcripts": [{"node": "implement", "text": res.text}],
        "revision_count": state.get("revision_count", 0) + (1 if feedback else 0),
    }


# ---------------------------------------------------------------------------
# NÚT 5 — Thẩm định SONG SONG bằng nhiều nhà cung cấp model.
#         Đây là điểm khác biệt lớn nhất so với một agent đơn lẻ.
# ---------------------------------------------------------------------------
async def cross_review(state: FleetState) -> dict:
    roles = ["reviewer", "security"] if state.get("risk") == "risky" else ["reviewer"]
    prompt = (
        "Xem diff so với origin/main. CHỈ ĐỌC.\n"
        "Mỗi phát hiện ghi đúng định dạng: [MỨC] file:dòng | mô tả | kịch bản hỏng.\n"
        "Mức: BLOCKER | CRITICAL | MAJOR | MINOR | NIT.\n"
        "Không có kịch bản hỏng cụ thể thì không phải phát hiện — đừng bịa."
    )
    results = await fanout(roles, _memory_prefix(state) + prompt, cwd=state["worktree"])

    findings = []
    transcripts = []
    for r in results:
        mine = parse_findings(r.role, r.text)
        findings.extend(mine)
        transcripts.append({"node": f"review:{r.role}", "text": r.text})
        # Chỉ ghi CHỮ KÝ (mức|file) vào vết chạy, không ghi nội dung phát hiện:
        # đủ để đếm lỗi lặp lại, không đủ để rò mã nguồn ra hệ thống log.
        _after_turn(
            state,
            f"review:{r.role}",
            r,
            blocker_sigs=[
                trajectory.finding_signature(f["severity"], f["location"])
                for f in mine
                if f["severity"] in ("BLOCKER", "CRITICAL")
            ],
        )
    return {"findings": findings, "transcripts": transcripts}


# ---------------------------------------------------------------------------
# NÚT 6 — Cổng kiểm soát. Hàm thuần tuý, không gọi model, luôn cho cùng kết quả.
# ---------------------------------------------------------------------------
def gate(state: FleetState) -> Literal["revise", "approval", "escalate"]:
    if not blockers(state):
        return "approval"
    if state.get("revision_count", 0) >= state.get("max_revisions", 2):
        # Đã sửa đủ số lần cho phép mà vẫn còn mục chặn → chuyển cho người.
        # Không bao giờ để agent tự lặp vô hạn: vừa tốn tiền vừa che giấu vấn đề thật.
        return "escalate"
    return "revise"


# ---------------------------------------------------------------------------
# NÚT 7 — Dừng chờ người. `interrupt()` đóng băng đồ thị và ghi trạng thái xuống
#         PostgreSQL; tiến trình được giải phóng. Khi người duyệt trả lời,
#         đồ thị chạy tiếp đúng từ đây.
# ---------------------------------------------------------------------------
def human_approval(state: FleetState) -> Command:
    decision = interrupt(
        {
            "type": "approval",
            "task_id": state["task_id"],
            "branch": state.get("branch"),
            "risk": state.get("risk"),
            "blockers": len(blockers(state)),
            "findings": state.get("findings", [])[:20],
            "question": "Duyệt mở pull request?",
        }
    )
    approved = bool(decision.get("approved"))
    by = decision.get("by", "unknown")
    trajectory.approval(state.get("task_id", ""), by=by, approved=approved,
                        profile=state.get("profile", ""))
    memory.append_step(state.get("task_id", ""), "approval",
                       f"{'duyệt' if approved else 'từ chối'} bởi {by}")

    if approved:
        return Command(
            goto="open_pr",
            update={"approved_by": by, "approval_note": decision.get("note", "")},
        )
    return Command(goto="finish", update={"outcome": "rejected",
                                          "approval_note": decision.get("note", "")})


# ---------------------------------------------------------------------------
# NÚT 8 — Mở PR. Xác định thuần tuý.
# ---------------------------------------------------------------------------
async def open_pr(state: FleetState) -> dict:
    wt, branch = state["worktree"], state["branch"]
    subprocess.run(["git", "-C", wt, "push", "-u", "origin", branch], check=True)
    out = subprocess.run(
        ["gh", "pr", "create", "--head", branch, "--draft",
         "--title", f"{state['task_id']}: {state['title']}",
         "--body", _pr_body(state)],
        cwd=wt, capture_output=True, text=True, check=True,
    )
    return {"pr_url": out.stdout.strip(), "outcome": "success"}


# ---------------------------------------------------------------------------
# NÚT 9 — Leo thang cho người khi tự động hoá đã hết cách.
# ---------------------------------------------------------------------------
def escalate(state: FleetState) -> dict:
    items = "\n".join(f"- [{f['severity']}] {f['location']}: {f['detail']}"
                      for f in blockers(state))
    # Leo thang là tín hiệu quan trọng nhất cho việc cải tiến harness: nó nói
    # đúng chỗ tự động hoá hết cách. Ghi riêng để `make metrics` đếm được.
    memory.append_step(state.get("task_id", ""), "escalate",
                       f"còn {len(blockers(state))} mục chặn sau "
                       f"{state.get('revision_count', 0)} lượt sửa")
    return {
        "escalated": True,
        "outcome": "blocked",
        "summary": (
            f"Đã sửa {state.get('revision_count')} lượt, vẫn còn "
            f"{len(blockers(state))} mục chặn. Cần người xử lý:\n{items}\n\n"
            f"Worktree giữ nguyên tại: {state.get('worktree')}"
        ),
    }


def finish(state: FleetState) -> dict:
    """Nút cuối cùng của MỌI nhánh — nơi duy nhất đóng sổ vết chạy.

    Đặt `run_finished` ở đây chứ không rải ra open_pr/escalate/rejected: một
    quy trình phải sinh ĐÚNG MỘT bản ghi run.end, nếu không mọi tỉ lệ trong
    fleet.metrics đều sai mẫu số.
    """
    task_id = state.get("task_id", "")
    started = float(state.get("started_at") or 0)
    duration_s = max(time.time() - started, 0.0) if started else 0.0

    trajectory.run_finished(
        task_id,
        outcome=str(state.get("outcome") or "partial"),
        duration_s=duration_s,
        repo=state.get("repo", ""),
        approved_by=state.get("approved_by", ""),
        revision_count=state.get("revision_count", 0),
        escalated=bool(state.get("escalated")),
        pr_url=state.get("pr_url", ""),
    )
    memory.append_step(task_id, "finish",
                       f"{state.get('outcome')} sau {round(duration_s)}s")

    return {"summary": state.get("summary") or f"Kết thúc với trạng thái: {state.get('outcome')}"}


def _pr_body(state: FleetState) -> str:
    lines = [f"## {state['title']}", "", f"Mã công việc: `{state['task_id']}`",
             f"Mức rủi ro: `{state.get('risk')}`",
             f"Số lượt sửa theo góp ý: {state.get('revision_count', 0)}",
             f"Người duyệt: {state.get('approved_by', '—')}", ""]
    if state.get("findings"):
        lines += ["### Phát hiện của thẩm định tự động", ""]
        lines += [f"- **{f['severity']}** `{f['location']}` — {f['detail']}"
                  for f in state["findings"][:30]]
    lines += ["", "_PR do Agent Fleet tạo. Vẫn cần người review trước khi merge._"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LẮP ĐỒ THỊ
# ---------------------------------------------------------------------------
def build_graph(checkpointer=None):
    g = StateGraph(FleetState)

    g.add_node("prepare", prepare)
    g.add_node("triage", triage)
    g.add_node("design", design)
    g.add_node("implement", implement)
    g.add_node("cross_review", cross_review)
    g.add_node("approval", human_approval)
    g.add_node("open_pr", open_pr)
    g.add_node("escalate", escalate)
    g.add_node("finish", finish)

    g.add_edge(START, "prepare")
    g.add_edge("prepare", "triage")

    # Nhánh theo mức rủi ro
    g.add_conditional_edges(
        "triage",
        lambda s: "design" if s.get("risk") == "risky" else "implement",
        {"design": "design", "implement": "implement"},
    )
    g.add_edge("design", "implement")
    g.add_edge("implement", "cross_review")

    # Cổng kiểm soát: sửa lại / chờ duyệt / leo thang
    g.add_conditional_edges(
        "cross_review", gate,
        {"revise": "implement", "approval": "approval", "escalate": "escalate"},
    )

    g.add_edge("open_pr", "finish")
    g.add_edge("escalate", "finish")
    g.add_edge("finish", END)

    return g.compile(checkpointer=checkpointer)


async def make_app():
    """Điểm vào cho `langgraph dev` / `langgraph build`.

    Checkpointer PostgreSQL là BẮT BUỘC ở môi trường thật: không có nó thì
    `interrupt()` mất trạng thái khi pod khởi động lại, và mọi lần chờ người
    duyệt đều biến thành chạy lại từ đầu.
    """
    dsn = os.environ["FLEET_CHECKPOINT_DSN"]
    saver = AsyncPostgresSaver.from_conn_string(dsn)
    async with saver as cp:
        await cp.setup()
        return build_graph(checkpointer=cp)


graph = build_graph()  # bản không checkpoint, dùng cho kiểm thử đơn vị


if __name__ == "__main__":
    async def _demo() -> None:
        app = await make_app()
        cfg = {"configurable": {"thread_id": "ENG-1421"}}
        state = initial_state(task_id="ENG-1421",
                              title="Thêm rate limit cho API public",
                              repo="/srv/repos/api")
        async for event in app.astream(state, cfg):
            print(event)

    asyncio.run(_demo())
