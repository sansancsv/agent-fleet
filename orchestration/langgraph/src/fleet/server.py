"""
=============================================================================
API của tầng điều phối — FastAPI mỏng đặt trước đồ thị LangGraph
-----------------------------------------------------------------------------
Vì sao tự viết server thay vì dùng `langgraph up` / LangGraph Server:

  1. `langgraph` (thư viện) KHÔNG kèm lệnh `langgraph`. CLI nằm ở gói riêng
     `langgraph-cli`. Đó là lý do container báo:
         exec: "langgraph": executable file not found in $PATH
  2. Kể cả cài đúng CLI, `langgraph up` dựng và chạy Docker Compose — chạy nó
     BÊN TRONG một container là sai tầng.
  3. Quan trọng nhất: n8n gọi `POST /runs/wait` và
     `GET /profiles/<tên>/authorize`. Đó là API của fleet này, không phải API
     của LangGraph Server. Tự viết thì hai bên khớp nhau theo đúng nghĩa đen.

Chạy:  uvicorn fleet.server:app --host 0.0.0.0 --port 8000
=============================================================================
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .graph import build_graph
from .state import blockers, initial_state

PROFILES_DIR = Path(os.environ.get("FLEET_PROFILES_DIR", "/fleet/profiles"))
CHECKPOINT_DSN = os.environ.get("FLEET_CHECKPOINT_DSN", "")

_state: dict[str, Any] = {"app": None, "cm": None}


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Mở checkpointer PostgreSQL một lần cho cả vòng đời tiến trình.

    Không có checkpointer thì `interrupt()` mất trạng thái khi pod khởi động
    lại, và mọi lần chờ người duyệt biến thành chạy lại từ đầu. Vì vậy khi
    thiếu DSN, ta chạy được nhưng nói thẳng ra trong log — không im lặng.
    """
    if CHECKPOINT_DSN:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        cm = AsyncPostgresSaver.from_conn_string(CHECKPOINT_DSN)
        saver = await cm.__aenter__()
        await saver.setup()
        _state["cm"] = cm
        _state["app"] = build_graph(checkpointer=saver)
    else:
        # Vẫn cần MỘT checkpointer, nếu không `interrupt()` và `aget_state()`
        # đều không dùng được. InMemorySaver cho hành vi giống hệt bản
        # PostgreSQL, chỉ khác: mất sạch khi tiến trình chết.
        from langgraph.checkpoint.memory import InMemorySaver

        print("[fleet] CẢNH BÁO: thiếu FLEET_CHECKPOINT_DSN — dùng bộ nhớ trong. "
              "Quy trình sẽ KHÔNG sống sót qua restart.", flush=True)
        _state["app"] = build_graph(checkpointer=InMemorySaver())
    try:
        yield
    finally:
        if _state["cm"] is not None:
            await _state["cm"].__aexit__(None, None, None)


app = FastAPI(title="Fleet Orchestrator", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Sức khoẻ
# ---------------------------------------------------------------------------
@app.get("/ok")
async def ok() -> dict:
    return {
        "ok": True,
        "checkpointer": "postgres" if CHECKPOINT_DSN else "memory",
        "profiles": sorted(p.stem for p in PROFILES_DIR.glob("*.yaml") if p.stem != "_schema")
        if PROFILES_DIR.is_dir() else [],
    }


# ---------------------------------------------------------------------------
# Hồ sơ phòng ban — n8n gọi vào đây để KIỂM QUYỀN TRƯỚC KHI tiêu token
# ---------------------------------------------------------------------------
def _load_profile(name: str) -> dict:
    if "/" in name or ".." in name:              # chặn path traversal
        raise HTTPException(400, "Tên hồ sơ không hợp lệ")
    path = PROFILES_DIR / f"{name}.yaml"
    if not path.is_file():
        raise HTTPException(404, f"Không có hồ sơ phòng ban '{name}'")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@app.get("/profiles")
async def list_profiles() -> dict:
    if not PROFILES_DIR.is_dir():
        return {"profiles": []}
    return {"profiles": sorted(p.stem for p in PROFILES_DIR.glob("*.yaml") if p.stem != "_schema")}


@app.get("/profiles/{name}/authorize")
async def authorize(name: str, requester: str = "") -> dict:
    profile = _load_profile(name)
    allowed = profile.get("requesters", []) or []
    ok_ = requester in allowed or "*" in allowed
    return {
        "allowed": ok_,
        "profile": name,
        "requester": requester,
        "dataClass": profile.get("dataClass"),
        "approvers": profile.get("approvers", []),
        "reason": "" if ok_ else f"'{requester}' không nằm trong danh sách của phòng {name}",
    }


# ---------------------------------------------------------------------------
# Chạy quy trình
# ---------------------------------------------------------------------------
class RunConfig(BaseModel):
    configurable: dict[str, Any] = Field(default_factory=dict)


class RunRequest(BaseModel):
    input: dict[str, Any]
    config: RunConfig = Field(default_factory=RunConfig)
    assistant_id: str = "fleet"


class ResumeRequest(BaseModel):
    approved: bool
    by: str = ""
    note: str = ""


def _thread_id(req: RunRequest) -> str:
    tid = req.config.configurable.get("thread_id") or req.input.get("task_id")
    if not tid:
        raise HTTPException(400, "Thiếu thread_id (hoặc task_id) — cần để tái hiện và chạy tiếp")
    return str(tid)


def _summarize(snapshot) -> dict:
    values = snapshot.values or {}
    pending = [t.interrupts for t in (snapshot.tasks or []) if getattr(t, "interrupts", None)]
    return {
        "status": "interrupted" if pending else "completed",
        "outcome": values.get("outcome"),
        "risk": values.get("risk"),
        "branch": values.get("branch"),
        "pr_url": values.get("pr_url"),
        "summary": values.get("summary"),
        "blockers": len(blockers(values)) if values else 0,
        "findings": (values.get("findings") or [])[:20],
        "interrupt": pending[0][0].value if pending else None,
    }


@app.post("/runs/wait")
async def run_wait(req: RunRequest) -> dict:
    """Chạy tới khi xong HOẶC tới điểm chờ người duyệt, rồi trả về ngay.

    n8n gọi endpoint này. Nếu trả `status: interrupted`, quy trình đang nằm
    trong PostgreSQL chờ người — gọi /runs/<thread_id>/resume để chạy tiếp.
    """
    graph = _state["app"]
    tid = _thread_id(req)
    cfg = {"configurable": {"thread_id": tid, **req.config.configurable}}

    payload = initial_state(**req.input)
    await graph.ainvoke(payload, cfg)
    snap = await graph.aget_state(cfg)
    return {"thread_id": tid, **_summarize(snap)}


@app.post("/runs/{thread_id}/resume")
async def run_resume(thread_id: str, decision: ResumeRequest) -> dict:
    """Người duyệt trả lời → đồ thị chạy tiếp đúng từ chỗ đã dừng."""
    from langgraph.types import Command

    graph = _state["app"]
    cfg = {"configurable": {"thread_id": thread_id}}
    await graph.ainvoke(Command(resume=decision.model_dump()), cfg)
    snap = await graph.aget_state(cfg)
    return {"thread_id": thread_id, **_summarize(snap)}


@app.get("/runs/{thread_id}")
async def run_state(thread_id: str) -> dict:
    graph = _state["app"]
    snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    if snap is None or not snap.values:
        raise HTTPException(404, f"Không có quy trình nào với thread_id '{thread_id}'")
    return {"thread_id": thread_id, **_summarize(snap)}
