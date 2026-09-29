"""Kiểm thử các điểm quyết định của đồ thị (graph.py).

CLAUDE.md gọi `gate()` là "hàm thuần tuý, có test" — file này là phần "có test".
Ba nhóm tính chất, cả ba đều là chỗ "model nêu, code quyết" dễ hỏng nhất:

  1. **Không hoàn tất ≠ sạch.** Một lượt thẩm định lỗi (timeout, runner bận 429,
     thiếu khoá, không có khối fleet-status...) cho ra 0 phát hiện, y như một
     lượt thẩm định sạch. `gate()` phải leo thang, không được cho qua.
  2. **Không có gì để thẩm định thì không thẩm định.** Implementer tự báo
     blocked/rejected, hoặc nhánh không có diff → leo thang ngay sau `implement`.
  3. **Đồ thị thật đi đúng đường.** Chạy cả đồ thị với agent giả: không cần
     model, không cần mạng; git thật chỉ dùng cho phép kiểm diff.
"""
from __future__ import annotations

import subprocess

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from fleet import acpx_client, graph, memory, trajectory
from fleet.acpx_client import AcpxError, AgentResult, _extract_status
from fleet.policies import required_reviewers, turn_problem
from fleet.state import initial_state


@pytest.fixture(autouse=True)
def _cach_ly_bo_nho(monkeypatch, tmp_path):
    # Chạy bằng root thì đường dẫn mặc định (/srv/fleet-memory, /var/log/fleet)
    # ghi được thật — test không được để lại dấu vết ở đó.
    monkeypatch.setattr(memory, "MEMORY_DIR", tmp_path / "memory")
    monkeypatch.setattr(trajectory, "TRAJECTORY_DIR", tmp_path / "trajectory")


def _status(outcome: str = "success", **extra: str) -> str:
    rows = [f"outcome: {outcome}", *(f"{k}: {v}" for k, v in extra.items())]
    return "\n```fleet-status\n" + "\n".join(rows) + "\n```\n"


def _res(role: str, text: str, exit_code: int = 0) -> AgentResult:
    # Như acpx_client: status được đọc từ khối fleet-status trong text.
    return AgentResult(role, text, exit_code, status=_extract_status(text))


def _review(role: str, ok: bool = True, rnd: int = 0) -> dict:
    return {"role": role, "round": rnd, "ok": ok, "reason": "" if ok else "thoát mã 1"}


BLOCKER = {"role": "reviewer", "severity": "BLOCKER", "location": "src/a.py:1", "detail": "d"}


def _state(risk: str = "standard", reviews=(), findings=(), **kw):
    fields = {"task_id": "T-1", "title": "Thêm rate limit", "repo": "/r", "worktree": "/wt",
              "base_ref": "origin/main", "risk": risk, "implement_problem": "", **kw}
    s = initial_state(**fields)
    s["reviews"] = list(reviews)
    s["findings"] = list(findings)
    return s


def _apply(state: dict, update: dict) -> dict:
    """Gộp kết quả một nút vào state như LangGraph làm (operator.add cho danh sách)."""
    for key, value in update.items():
        if key in ("transcripts", "findings", "reviews"):
            state[key] = state.get(key, []) + value
        else:
            state[key] = value
    return state


# ---------------------------------------------------------------------------
# 1. Định nghĩa "lượt hoàn tất" — hàm thuần tuý trong policies.py
# ---------------------------------------------------------------------------
class TestTurnProblem:
    @pytest.mark.parametrize("outcome", ["success", "partial", "Success", "`success`"])
    def test_hoan_tat(self, outcome):
        assert turn_problem(0, {"outcome": outcome}) == ""

    def test_thoat_ma_khac_0(self):
        # Khối trạng thái nói success cũng không cứu được một lượt thoát lỗi.
        assert "thoát mã 1" in turn_problem(1, {"outcome": "success"})

    def test_thieu_khoi_trang_thai(self):
        assert turn_problem(0, {}) == "thiếu khối fleet-status"

    def test_khoi_thieu_outcome(self):
        assert "thiếu outcome" in turn_problem(0, {"role": "reviewer"})

    @pytest.mark.parametrize("outcome", ["blocked", "rejected"])
    def test_blocked_rejected(self, outcome):
        assert turn_problem(0, {"outcome": outcome}) == f"outcome: {outcome}"

    @pytest.mark.parametrize("outcome", ["success | partial | blocked | rejected", "done", ""])
    def test_nhan_la_thi_nghieng_ve_chat(self, outcome):
        # Chép nguyên dòng mẫu, hay tự đặt nhãn — không nhận dạng được thì
        # không được tính là hoàn tất.
        assert turn_problem(0, {"outcome": outcome})


class TestRequiredReviewers:
    def test_theo_muc_rui_ro(self):
        assert required_reviewers("trivial") == ["reviewer"]
        assert required_reviewers("standard") == ["reviewer"]
        assert required_reviewers("risky") == ["reviewer", "security"]

    @pytest.mark.parametrize("risk", [None, "", "khong-ro"])
    def test_rui_ro_la_thi_coi_nhu_risky(self, risk):
        assert required_reviewers(risk) == ["reviewer", "security"]


# ---------------------------------------------------------------------------
# 2. gate() — hàm thuần tuý
# ---------------------------------------------------------------------------
class TestGate:
    def test_tham_dinh_sach_thi_cho_duyet(self):
        assert graph.gate(_state(reviews=[_review("reviewer")])) == "approval"

    def test_reviewer_loi_thi_leo_thang(self):
        assert graph.gate(_state(reviews=[_review("reviewer", ok=False)])) == "escalate"

    def test_khong_co_ban_ghi_tham_dinh_thi_leo_thang(self):
        # Vắng mặt không phải bằng chứng của thẩm định sạch.
        assert graph.gate(_state()) == "escalate"

    def test_risky_thieu_security_thi_leo_thang(self):
        assert graph.gate(_state("risky", reviews=[_review("reviewer")])) == "escalate"

    def test_ban_ghi_cua_vong_cu_khong_duoc_tinh(self):
        s = _state(reviews=[_review("reviewer", rnd=0)], revision_count=1)
        assert graph.gate(s) == "escalate"

    def test_tham_dinh_loi_duoc_xet_truoc_muc_chan(self):
        s = _state("risky", reviews=[_review("reviewer"), _review("security", ok=False)],
                   findings=[BLOCKER])
        assert graph.gate(s) == "escalate"

    def test_co_muc_chan_thi_sua_lai(self):
        s = _state(reviews=[_review("reviewer")], findings=[BLOCKER])
        assert graph.gate(s) == "revise"

    def test_het_luot_sua_thi_leo_thang(self):
        s = _state(reviews=[_review("reviewer", rnd=2)], findings=[BLOCKER], revision_count=2)
        assert graph.gate(s) == "escalate"


# ---------------------------------------------------------------------------
# 3. cross_review ghi lại lượt nào hoàn tất
# ---------------------------------------------------------------------------
class TestCrossReview:
    async def test_reviewer_nem_loi_thi_gate_leo_thang(self, monkeypatch):
        # Đúng kịch bản đã tái hiện: agent-runner trả 429 (mặc định chỉ 4 lượt
        # đồng thời), `fanout` đổi exception thành AgentResult(exit_code=1).
        async def ban(role, prompt, cwd, **_kw):
            raise AcpxError(f"{role}: agent-runner trả 429: runner đang bận")

        monkeypatch.setattr(acpx_client, "run_role", ban)
        s = _state("risky")
        s = _apply(s, await graph.cross_review(s))

        assert graph.gate(s) == "escalate"
        assert [r["ok"] for r in s["reviews"]] == [False, False]
        assert "429" in s["reviews"][0]["reason"]

    @pytest.mark.parametrize(
        ("text", "ly_do"),
        [
            ("Không có phát hiện nào.", "thiếu khối fleet-status"),
            ("Không xem được diff." + _status("blocked"), "outcome: blocked"),
        ],
        ids=["thieu-khoi", "tu-bao-blocked"],
    )
    async def test_luot_khong_hoan_tat_thi_leo_thang(self, monkeypatch, text, ly_do):
        async def reviewer(role, prompt, cwd, **_kw):
            return _res(role, text)

        monkeypatch.setattr(acpx_client, "run_role", reviewer)
        s = _state()
        s = _apply(s, await graph.cross_review(s))
        assert graph.gate(s) == "escalate"
        assert s["reviews"] == [{"role": "reviewer", "round": 0, "ok": False, "reason": ly_do}]

    async def test_hoan_tat_va_sach_thi_cho_duyet(self, monkeypatch):
        async def reviewer(role, prompt, cwd, **_kw):
            return _res(role, "Không có phát hiện nào." + _status())

        monkeypatch.setattr(acpx_client, "run_role", reviewer)
        s = _state()
        s = _apply(s, await graph.cross_review(s))
        assert graph.gate(s) == "approval"

    async def test_prompt_doi_khoi_trang_thai_va_dung_nhanh_goc(self, monkeypatch):
        prompts = []

        async def reviewer(role, prompt, cwd, **_kw):
            prompts.append(prompt)
            return _res(role, _status())

        monkeypatch.setattr(acpx_client, "run_role", reviewer)
        await graph.cross_review(_state(base_ref="origin/master"))
        assert "origin/master" in prompts[0] and "origin/main" not in prompts[0]
        assert "```fleet-status" in prompts[0]


# ---------------------------------------------------------------------------
# 4. Sau implement: dừng khi implementer không giao được gì
# ---------------------------------------------------------------------------
class TestSauImplement:
    def test_canh_sau_implement_la_ham_thuan_tuy(self):
        assert graph.after_implement({"implement_problem": ""}) == "cross_review"
        assert graph.after_implement({"implement_problem": "outcome: blocked"}) == "escalate"
        # Chưa có kết luận nào thì cũng không đi tiếp.
        assert graph.after_implement({}) == "escalate"

    @pytest.mark.parametrize(
        ("text", "diff", "van_de"),
        [
            ("Thiếu thông tin." + _status("blocked", next="Bảng orders dùng schema nào?"),
             "", "outcome: blocked"),
            ("Ngoài quyền của tôi." + _status("rejected"), "", "outcome: rejected"),
            ("Đã sửa xong." + _status(), "nhánh không có thay đổi nào", "nhánh không có thay đổi"),
            ("Đã commit.", "", "thiếu khối fleet-status"),
        ],
        ids=["blocked", "rejected", "diff-rong", "thieu-khoi"],
    )
    async def test_ghi_ly_do_dung(self, monkeypatch, text, diff, van_de):
        async def implementer(role, prompt, cwd, **_kw):
            return _res(role, text)

        monkeypatch.setattr(graph, "run_role", implementer)
        monkeypatch.setattr(graph, "_diff_problem", lambda _s: diff)
        out = await graph.implement(_state())
        assert out["implement_problem"].startswith(van_de)
        assert graph.after_implement(out) == "escalate"

    async def test_cau_hoi_cua_agent_lay_tu_dong_next(self, monkeypatch):
        async def implementer(role, prompt, cwd, **_kw):
            text = "Thiếu thông tin." + _status("blocked", next="Bảng orders dùng schema nào?")
            return _res(role, text)

        monkeypatch.setattr(graph, "run_role", implementer)
        out = await graph.implement(_state())
        assert out["implement_question"] == "Bảng orders dùng schema nào?"

    async def test_hoan_tat_va_co_diff_thi_di_tiep(self, monkeypatch):
        async def implementer(role, prompt, cwd, **_kw):
            return _res(role, "Đã commit." + _status())

        monkeypatch.setattr(graph, "run_role", implementer)
        monkeypatch.setattr(graph, "_diff_problem", lambda _s: "")
        out = await graph.implement(_state())
        assert out["implement_problem"] == "" and out["implement_question"] == ""
        assert graph.after_implement(out) == "cross_review"


class TestKiemDiff:
    """`_diff_problem` trên một repo git thật — đúng lệnh sẽ chạy trong container."""

    @staticmethod
    def _git(repo, *args):
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@x.vn",
             "-c", "commit.gpgsign=false", *args],
            check=True, capture_output=True,
        )

    @pytest.fixture()
    def repo(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        self._git(repo, "init", "-q")
        (repo / "a.txt").write_text("1\n", encoding="utf-8")
        self._git(repo, "add", "a.txt")
        self._git(repo, "commit", "-q", "-m", "base")
        # Giống worktree thật: nhánh gốc là một ref của remote.
        self._git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        return repo

    @staticmethod
    def _check(repo, base="origin/main"):
        return graph._diff_problem({"repo": str(repo), "worktree": str(repo), "base_ref": base})

    def test_chua_commit_gi_thi_la_rong(self, repo):
        assert "không có thay đổi nào đã commit" in self._check(repo)

    def test_sua_ma_chua_commit_van_la_rong(self, repo):
        # PR chỉ mang theo commit; thay đổi nằm trong working tree thì không.
        (repo / "a.txt").write_text("2\n", encoding="utf-8")
        assert "không có thay đổi nào đã commit" in self._check(repo)

    def test_co_commit_moi_thi_di_tiep(self, repo):
        (repo / "a.txt").write_text("2\n", encoding="utf-8")
        self._git(repo, "commit", "-q", "-am", "feat: x")
        assert self._check(repo) == ""

    def test_loi_git_cung_la_ly_do_dung(self, repo):
        assert "không kiểm được diff" in self._check(repo, base="origin/khong-co")


# ---------------------------------------------------------------------------
# 5. Cả đồ thị, với agent giả
# ---------------------------------------------------------------------------
class FakeFleet:
    """Agent giả cho mọi vai trò; `replies[vai trò](prompt)` trả AgentResult hoặc exception."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.replies = {
            "orchestrator": lambda p: _res("orchestrator", "standard"),
            "architect": lambda p: _res("architect", "Đã viết ADR." + _status()),
            "implementer": lambda p: _res("implementer", "Đã commit." + _status()),
            "reviewer": lambda p: _res("reviewer", "Không có phát hiện nào." + _status()),
            "security": lambda p: _res("security", "Không có phát hiện nào." + _status()),
        }

    async def __call__(self, role, prompt, cwd=None, **_kw):
        self.calls.append((role, prompt))
        reply = self.replies[role](prompt)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    def roles(self) -> list[str]:
        return [role for role, _ in self.calls]


@pytest.fixture()
def fleet(monkeypatch):
    fake = FakeFleet()

    async def prepare(_state):
        return {"branch": "feat/t-9", "worktree": "/wt", "base_ref": "origin/main"}

    monkeypatch.setattr(graph, "prepare", prepare)
    monkeypatch.setattr(graph, "run_role", fake)
    monkeypatch.setattr(acpx_client, "run_role", fake)   # fanout gọi qua module acpx_client
    monkeypatch.setattr(graph, "_diff_problem", lambda _s: "")
    return fake


async def _run(**kw):
    app = graph.build_graph(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "T-9"}}
    await app.ainvoke(initial_state(task_id="T-9", title="Thêm rate limit", repo="/r", **kw), cfg)
    return await app.aget_state(cfg)


class TestDoThi:
    async def test_duong_vui_dung_cho_nguoi_duyet(self, fleet):
        snap = await _run()
        assert snap.next == ("approval",)
        assert snap.tasks[0].interrupts[0].value["blockers"] == 0
        assert fleet.roles() == ["orchestrator", "implementer", "reviewer"]

    async def test_implementer_blocked_khong_toi_cross_review(self, fleet):
        fleet.replies["implementer"] = lambda p: _res(
            "implementer",
            "Thiếu thông tin." + _status("blocked", next="Bảng orders dùng schema nào?"),
        )
        snap = await _run()

        assert snap.next == ()                           # kết thúc, không chờ duyệt
        assert "reviewer" not in fleet.roles() and "security" not in fleet.roles()
        values = snap.values
        assert values["escalated"] is True and values["outcome"] == "blocked"
        assert "Bảng orders dùng schema nào?" in values["summary"]

    async def test_diff_rong_khong_toi_cross_review(self, fleet, monkeypatch):
        monkeypatch.setattr(graph, "_diff_problem",
                            lambda _s: "nhánh không có thay đổi nào đã commit so với origin/main")
        snap = await _run()
        assert snap.next == ()
        assert "reviewer" not in fleet.roles()
        assert "không có thay đổi nào" in snap.values["summary"]

    async def test_reviewer_loi_thi_leo_thang_khong_cho_duyet(self, fleet):
        fleet.replies["reviewer"] = lambda p: AcpxError("reviewer: vượt quá 1800s")
        snap = await _run()

        assert snap.next == ()
        assert snap.values["escalated"] is True
        assert "reviewer" in snap.values["summary"] and "1800s" in snap.values["summary"]

    async def test_risky_chay_ca_security(self, fleet):
        fleet.replies["orchestrator"] = lambda p: _res("orchestrator", "risky")
        snap = await _run()
        assert snap.next == ("approval",)
        assert sorted(fleet.roles()[-2:]) == ["reviewer", "security"]
