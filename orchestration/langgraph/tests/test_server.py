"""Kiểm thử tầng API của bộ điều phối.

Ba thứ được kiểm ở đây:

  1. Server khởi động được bằng uvicorn (gói `langgraph` KHÔNG có lệnh
     `langgraph`; `langgraph up` dựng Docker Compose nên không dùng trong
     container được).
  2. Các endpoint mà n8n gọi tồn tại đúng như workflow khai báo:
     `POST /runs/wait`, `GET /profiles/<tên>/authorize` và
     `POST /profiles/<tên>/run`.
  3. Ba chốt bảo vệ: Bearer token trên mọi endpoint trừ /ok; người duyệt ở
     `/resume` phải nằm trong `approvers` của hồ sơ; và chốt dataClass — lượt
     agent phòng ban chỉ chạy khi backend của nó được mức dữ liệu của hồ sơ
     cho phép. Không có chốt cuối, dữ liệu `restricted` từng đi thẳng tới Gemini.

Vòng chờ-người-duyệt được kiểm bằng một đồ thị nhỏ thay cho đồ thị thật, và
agent-runner được thay bằng bản giả ghi lại lượt gọi — test không cần git,
không cần model, không cần mạng.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from fleet import server, trajectory
from fleet.acpx_client import AcpxError, AgentResult

TOKEN = "test-token-123"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class MiniState(TypedDict, total=False):
    task_id: str
    title: str
    profile: str
    outcome: str
    summary: str


def _mini_graph():
    def ask(_s: MiniState) -> Command:
        d = interrupt({"question": "Duyệt không?"})
        if d.get("approved"):
            return Command(goto="done", update={"outcome": "success"})
        return Command(goto="done", update={"outcome": "rejected"})

    def done(s: MiniState) -> dict:
        return {"summary": f"kết thúc: {s.get('outcome')}"}

    g = StateGraph(MiniState)
    g.add_node("ask", ask)
    g.add_node("done", done)
    g.add_edge(START, "ask")
    g.add_edge("done", END)
    return g.compile(checkpointer=InMemorySaver())


@pytest.fixture()
def client(monkeypatch, tmp_path):
    (tmp_path / "demo.yaml").write_text(
        "name: Demo\ndataClass: internal\nrequesters: ['an@x.vn']\napprovers: ['sep@x.vn']\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "PROFILES_DIR", tmp_path)
    monkeypatch.setattr(trajectory, "TRAJECTORY_DIR", tmp_path / "vet")  # không ghi vào /var/log
    monkeypatch.setenv("LANGGRAPH_TOKEN", TOKEN)
    with TestClient(server.app) as c:
        server._state["app"] = _mini_graph()   # thay đồ thị thật bằng đồ thị nhỏ
        yield c


@pytest.fixture()
def runner(monkeypatch):
    """agent-runner giả: ghi lại mọi lượt agent được gọi, trả một câu trả lời cố định."""
    calls: list[dict] = []

    async def fake_run_role(role, prompt, cwd, *, permission=None, session=None, timeout_s=1800):
        calls.append({"role": role, "prompt": prompt, "cwd": cwd, "permission": permission})
        return AgentResult(role=role, text="Kết luận: ổn.", exit_code=0,
                           status={"outcome": "success"}, duration_ms=7)

    monkeypatch.setattr(server, "run_role", fake_run_role)
    return calls


def _ho_so(directory, name: str, data_class: str | None, requesters=("*",)) -> None:
    lines = [f"name: {name}", f"requesters: {list(requesters)!r}", "approvers: ['sep@x.vn']"]
    if data_class is not None:
        lines.append(f"dataClass: {data_class}")
    (directory / f"{name}.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _dept(client, profile: str, *, request="Tóm tắt chi phí quý 3", requester="an@x.vn",
          task_id="REQ-1", headers=AUTH):
    return client.post(
        f"/profiles/{profile}/run",
        json={"task_id": task_id, "requester": requester, "request": request},
        headers=headers,
    )


def _start(client, task_id: str, profile: str = "demo"):
    return client.post(
        "/runs/wait",
        json={"input": {"task_id": task_id, "title": "x", "profile": profile}},
        headers=AUTH,
    )


class TestHealth:
    def test_ok_khong_can_token(self, client):
        body = client.get("/ok").json()
        assert body["ok"] is True and body["auth"] == "token"


class TestAuth:
    def test_thieu_token_bi_401(self, client):
        assert client.get("/profiles").status_code == 401

    def test_sai_token_bi_403(self, client):
        r = client.get("/profiles", headers={"Authorization": "Bearer sai"})
        assert r.status_code == 403

    def test_dung_token_thi_qua(self, client):
        assert client.get("/profiles", headers=AUTH).status_code == 200

    def test_khong_cau_hinh_token_thi_dong_hoan_toan(self, client, monkeypatch):
        # Fail closed: thiếu cấu hình không được biến thành "mở cho tất cả".
        monkeypatch.delenv("LANGGRAPH_TOKEN")
        assert client.get("/profiles", headers=AUTH).status_code == 503
        assert client.get("/ok").json()["auth"] == "MISSING"


class TestAuthorize:
    def test_duoc_phep(self, client):
        r = client.get("/profiles/demo/authorize", params={"requester": "an@x.vn"}, headers=AUTH)
        assert r.json()["allowed"] is True

    def test_bi_chan_co_ly_do(self, client):
        r = client.get("/profiles/demo/authorize", params={"requester": "la@x.vn"}, headers=AUTH)
        body = r.json()
        assert body["allowed"] is False and body["reason"]

    def test_ho_so_khong_ton_tai(self, client):
        assert client.get("/profiles/khong-co/authorize", headers=AUTH).status_code == 404

    def test_chan_path_traversal(self, client):
        r = client.get("/profiles/..%2F..%2Fetc%2Fpasswd/authorize", headers=AUTH)
        assert r.status_code in (400, 404)


class TestRuns:
    def test_thieu_thread_id_bi_tu_choi(self, client):
        r = client.post("/runs/wait", json={"input": {"title": "x"}}, headers=AUTH)
        assert r.status_code == 400

    def test_dung_cho_nguoi_roi_chay_tiep(self, client):
        r = _start(client, "T-1")
        assert r.status_code == 200
        assert r.json()["status"] == "interrupted"      # đang chờ người duyệt

        r = client.post("/runs/T-1/resume", json={"approved": True, "by": "sep@x.vn"}, headers=AUTH)
        body = r.json()
        assert body["status"] == "completed" and body["outcome"] == "success"

    def test_tu_choi_thi_ket_thuc_o_trang_thai_rejected(self, client):
        _start(client, "T-2")
        body = client.post(
            "/runs/T-2/resume", json={"approved": False, "by": "sep@x.vn"}, headers=AUTH
        ).json()
        assert body["outcome"] == "rejected"

    def test_doc_lai_trang_thai(self, client):
        _start(client, "T-3")
        assert client.get("/runs/T-3", headers=AUTH).json()["status"] == "interrupted"

    def test_thread_khong_ton_tai(self, client):
        assert client.get("/runs/khong-co", headers=AUTH).status_code == 404


class TestApprover:
    """Chốt người duyệt: token API chứng minh 'n8n gọi', không chứng minh 'CFO duyệt'."""

    def test_nguoi_khong_trong_danh_sach_bi_403(self, client):
        _start(client, "A-1")
        r = client.post("/runs/A-1/resume", json={"approved": True, "by": "ke-la@x.vn"}, headers=AUTH)
        assert r.status_code == 403
        # Thread vẫn đang chờ — quyết định bị từ chối không làm nó chạy tiếp.
        assert client.get("/runs/A-1", headers=AUTH).json()["status"] == "interrupted"

    def test_thieu_by_bi_403(self, client):
        _start(client, "A-2")
        r = client.post("/runs/A-2/resume", json={"approved": True}, headers=AUTH)
        assert r.status_code == 403

    def test_tu_choi_cung_phai_la_nguoi_duyet(self, client):
        _start(client, "A-3")
        r = client.post("/runs/A-3/resume", json={"approved": False, "by": "ke-la@x.vn"}, headers=AUTH)
        assert r.status_code == 403

    def test_resume_thread_da_xong_bi_409(self, client):
        _start(client, "A-4")
        client.post("/runs/A-4/resume", json={"approved": True, "by": "sep@x.vn"}, headers=AUTH)
        r = client.post("/runs/A-4/resume", json={"approved": True, "by": "sep@x.vn"}, headers=AUTH)
        assert r.status_code == 409

    def test_ho_so_khong_ton_tai_thi_khong_duyet_duoc(self, client):
        _start(client, "A-5", profile="khong-co")
        r = client.post("/runs/A-5/resume", json={"approved": True, "by": "sep@x.vn"}, headers=AUTH)
        assert r.status_code == 404


class TestDeptGate:
    """Chốt dataClass: mức nhạy cảm của hồ sơ quyết định backend nào được thấy dữ liệu.

    Lượt phòng ban chạy vai trò `analyst` — Gemini theo ROLE_BACKENDS. Trước khi
    có chốt này, n8n gửi thẳng mọi phòng ban ngoài kỹ thuật tới đó, kể cả
    finance/legal (restricted) và support (confidential).
    """

    @pytest.mark.parametrize("data_class", ["restricted", "confidential"])
    def test_backend_khong_duoc_phep_thi_khong_co_luot_agent_nao(
        self, client, runner, tmp_path, data_class
    ):
        _ho_so(tmp_path, "mat", data_class)
        r = _dept(client, "mat")
        assert r.status_code == 403
        assert runner == []          # dữ liệu không rời khỏi đây
        detail = r.json()["detail"]
        assert f"'{data_class}'" in detail and "'gemini'" in detail and "analyst" in detail

    def test_loi_neu_ro_backend_nao_moi_duoc_phep(self, client, runner, tmp_path):
        _ho_so(tmp_path, "tai-chinh", "restricted")
        detail = _dept(client, "tai-chinh").json()["detail"]
        assert "Được phép: local-llm" in detail

    @pytest.mark.parametrize("data_class", [None, "bi-mat", "Internal"])
    def test_dataclass_thieu_hoac_la_thi_tu_choi(self, client, runner, tmp_path, data_class):
        # Fail closed: hồ sơ quên khai dataClass không được coi là "không ràng buộc".
        _ho_so(tmp_path, "mo-ho", data_class)
        assert _dept(client, "mo-ho").status_code == 403
        assert runner == []

    def test_noi_bo_thi_chay_dung_mot_luot_chi_doc(self, client, runner, tmp_path):
        _ho_so(tmp_path, "mo", "internal")
        r = _dept(client, "mo", request="Viết email ra mắt tính năng X")
        assert r.status_code == 200
        body = r.json()
        assert body["dataClass"] == "internal" and body["backend"] == "gemini"
        assert body["role"] == "analyst" and body["text"] == "Kết luận: ổn."
        assert body["exit_code"] == 0 and body["outcome"] == "success"
        assert len(runner) == 1
        call = runner[0]
        assert call["role"] == "analyst" and call["permission"] == "deny-all"
        assert ('<untrusted source="requester">\nViết email ra mắt tính năng X\n</untrusted>'
                in call["prompt"])

    def test_quyet_dinh_theo_backend_that_cua_vai_tro(self, client, runner, tmp_path, monkeypatch):
        # Chốt tra ROLE_BACKENDS, không cấm cứng Gemini: nếu vai trò phòng ban
        # chạy trên backend được phép thì hồ sơ confidential đi qua được.
        monkeypatch.setitem(server.ROLE_BACKENDS, "analyst", ("claude", "deny-all"))
        _ho_so(tmp_path, "mat", "confidential")
        r = _dept(client, "mat")
        assert r.status_code == 200 and r.json()["backend"] == "claude"
        assert len(runner) == 1

    def test_nguoi_gui_ngoai_danh_sach_bi_403(self, client, runner, tmp_path):
        # Kiểm lại ở đây dù n8n đã gọi /authorize — đây là chỗ tiêu token.
        _ho_so(tmp_path, "mo", "internal", requesters=["an@x.vn"])
        assert _dept(client, "mo", requester="la@x.vn").status_code == 403
        assert runner == []

    def test_ho_so_khong_ton_tai(self, client, runner):
        assert _dept(client, "khong-co").status_code == 404
        assert runner == []

    def test_can_token(self, client, runner, tmp_path):
        _ho_so(tmp_path, "mo", "internal")
        assert _dept(client, "mo", headers={}).status_code == 401
        assert runner == []

    def test_yeu_cau_rong_bi_400(self, client, runner, tmp_path):
        _ho_so(tmp_path, "mo", "internal")
        assert _dept(client, "mo", request="   ").status_code == 400
        assert runner == []

    def test_thieu_task_id_bi_422(self, client, runner, tmp_path):
        _ho_so(tmp_path, "mo", "internal")
        assert _dept(client, "mo", task_id="").status_code == 422
        assert runner == []

    def test_runner_hong_thi_502(self, client, tmp_path, monkeypatch):
        async def hong(*_a, **_k):
            raise AcpxError("analyst: không gọi được agent-runner")

        monkeypatch.setattr(server, "run_role", hong)
        _ho_so(tmp_path, "mo", "internal")
        r = _dept(client, "mo")
        assert r.status_code == 502 and "agent-runner" in r.json()["detail"]

    def test_tu_choi_de_lai_dau_vet_ben(self, client, runner, tmp_path, capsys):
        _ho_so(tmp_path, "tai-chinh", "restricted")
        _dept(client, "tai-chinh", task_id="REQ-9", requester="cfo@x.vn")

        audit = [json.loads(line) for line in capsys.readouterr().out.splitlines()
                 if '"policy.decision"' in line]
        assert audit and audit[-1]["allowed"] is False
        assert audit[-1]["data_class"] == "restricted" and audit[-1]["backend"] == "gemini"

        denied = [e for e in trajectory.read_all(tmp_path / "vet")
                  if e.get("event") == "permission.denied"]
        assert denied and denied[-1]["task_id"] == "REQ-9"
        assert denied[-1]["by"] == "cfo@x.vn" and denied[-1]["profile"] == "tai-chinh"
        assert denied[-1]["reason"] == "backend-not-allowed:gemini"

    def test_cho_qua_cung_ghi_audit(self, client, runner, tmp_path, capsys):
        _ho_so(tmp_path, "mo", "internal")
        _dept(client, "mo")
        audit = [json.loads(line) for line in capsys.readouterr().out.splitlines()
                 if '"policy.decision"' in line]
        assert audit and audit[-1]["allowed"] is True and audit[-1]["backend"] == "gemini"
