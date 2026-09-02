"""Kiểm thử tầng API của bộ điều phối.

Ba thứ được kiểm ở đây, và cả ba đều là chỗ đã từng hỏng thật:

  1. Server khởi động được bằng uvicorn (gói `langgraph` KHÔNG có lệnh
     `langgraph`; `langgraph up` dựng Docker Compose nên không dùng trong
     container được).
  2. Các endpoint mà n8n gọi tồn tại đúng như workflow khai báo:
     `POST /runs/wait` và `GET /profiles/<tên>/authorize`.
  3. Hai chốt bảo vệ: Bearer token trên mọi endpoint trừ /ok, và người duyệt
     ở `/resume` phải nằm trong `approvers` của hồ sơ. Không có hai chốt này,
     bất kỳ tiến trình nào trong mạng nội bộ cũng "duyệt" được PR.

Vòng chờ-người-duyệt được kiểm bằng một đồ thị nhỏ thay cho đồ thị thật, để
test không cần git, không cần model, không cần mạng.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from fleet import server

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
    monkeypatch.setenv("LANGGRAPH_TOKEN", TOKEN)
    with TestClient(server.app) as c:
        server._state["app"] = _mini_graph()   # thay đồ thị thật bằng đồ thị nhỏ
        yield c


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
