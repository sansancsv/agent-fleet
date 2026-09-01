"""Kiểm thử tầng API của bộ điều phối.

Hai thứ được kiểm ở đây, và cả hai đều là chỗ đã từng hỏng thật:

  1. Server khởi động được bằng uvicorn (gói `langgraph` KHÔNG có lệnh
     `langgraph`; `langgraph up` dựng Docker Compose nên không dùng trong
     container được).
  2. Các endpoint mà n8n gọi tồn tại đúng như workflow khai báo:
     `POST /runs/wait` và `GET /profiles/<tên>/authorize`.

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


class MiniState(TypedDict, total=False):
    task_id: str
    title: str
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
    with TestClient(server.app) as c:
        server._state["app"] = _mini_graph()   # thay đồ thị thật bằng đồ thị nhỏ
        yield c


class TestHealth:
    def test_ok(self, client):
        assert client.get("/ok").json()["ok"] is True


class TestAuthorize:
    def test_duoc_phep(self, client):
        r = client.get("/profiles/demo/authorize", params={"requester": "an@x.vn"})
        assert r.json()["allowed"] is True

    def test_bi_chan_co_ly_do(self, client):
        r = client.get("/profiles/demo/authorize", params={"requester": "la@x.vn"})
        body = r.json()
        assert body["allowed"] is False and body["reason"]

    def test_ho_so_khong_ton_tai(self, client):
        assert client.get("/profiles/khong-co/authorize").status_code == 404

    def test_chan_path_traversal(self, client):
        assert client.get("/profiles/..%2F..%2Fetc%2Fpasswd/authorize").status_code in (400, 404)


class TestRuns:
    def test_thieu_thread_id_bi_tu_choi(self, client):
        r = client.post("/runs/wait", json={"input": {"title": "x"}})
        assert r.status_code == 400

    def test_dung_cho_nguoi_roi_chay_tiep(self, client):
        r = client.post("/runs/wait", json={"input": {"task_id": "T-1", "title": "x"}})
        assert r.status_code == 200
        assert r.json()["status"] == "interrupted"      # đang chờ người duyệt

        r = client.post("/runs/T-1/resume", json={"approved": True, "by": "sep@x.vn"})
        body = r.json()
        assert body["status"] == "completed" and body["outcome"] == "success"

    def test_tu_choi_thi_ket_thuc_o_trang_thai_rejected(self, client):
        client.post("/runs/wait", json={"input": {"task_id": "T-2", "title": "x"}})
        body = client.post("/runs/T-2/resume", json={"approved": False}).json()
        assert body["outcome"] == "rejected"

    def test_doc_lai_trang_thai(self, client):
        client.post("/runs/wait", json={"input": {"task_id": "T-3", "title": "x"}})
        assert client.get("/runs/T-3").json()["status"] == "interrupted"

    def test_thread_khong_ton_tai(self, client):
        assert client.get("/runs/khong-co").status_code == 404
