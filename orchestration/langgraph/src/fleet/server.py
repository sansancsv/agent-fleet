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

Hai chốt bảo vệ của API này (cả hai đều fail closed):

  * Mọi endpoint trừ /ok đòi `Authorization: Bearer $LANGGRAPH_TOKEN`. Thiếu
    biến môi trường thì API trả 503 cho mọi yêu cầu — không âm thầm mở.
  * `/runs/<id>/resume` là chốt "người duyệt". Trường `by` phải nằm trong
    `approvers` của hồ sơ phòng ban gắn với thread đó; nếu không → 403. Đây là
    điểm biến "agent đề xuất" thành "người quyết định", nên nó không được phép
    tin vào bất kỳ ai gửi `approved: true`.

Chạy:  uvicorn fleet.server:app --host 0.0.0.0 --port 8000
=============================================================================
"""

from __future__ import annotations

import hmac
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import trajectory
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


# ---------------------------------------------------------------------------
# Xác thực — đọc token LÚC GỌI (không lúc import) để test và xoay khoá được.
# ---------------------------------------------------------------------------
def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = os.environ.get("LANGGRAPH_TOKEN", "")
    if not expected:
        # Fail closed: cấu hình thiếu là lỗi vận hành, không phải lý do để mở API.
        raise HTTPException(503, "LANGGRAPH_TOKEN chưa được cấu hình — API từ chối mọi yêu cầu")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Thiếu Authorization: Bearer <token>")
    if not hmac.compare_digest(authorization[7:].strip(), expected):
        raise HTTPException(403, "Token không hợp lệ")


Protected = Depends(require_token)


def _audit(event: str, **fields: Any) -> None:
    """Một dòng JSON ra stdout — Docker/K8s gom về hệ thống log tập trung."""
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    print(json.dumps(rec, ensure_ascii=False), file=sys.stdout, flush=True)


app = FastAPI(title="Fleet Orchestrator", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Sức khoẻ — endpoint DUY NHẤT không cần token (healthcheck của compose/K8s).
# Không lộ gì ngoài trạng thái checkpointer và tên hồ sơ.
# ---------------------------------------------------------------------------
@app.get("/ok")
async def ok() -> dict:
    return {
        "ok": True,
        "checkpointer": "postgres" if CHECKPOINT_DSN else "memory",
        "auth": "token" if os.environ.get("LANGGRAPH_TOKEN") else "MISSING",
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


@app.get("/profiles", dependencies=[Protected])
async def list_profiles() -> dict:
    if not PROFILES_DIR.is_dir():
        return {"profiles": []}
    return {"profiles": sorted(p.stem for p in PROFILES_DIR.glob("*.yaml") if p.stem != "_schema")}


@app.get("/profiles/{name}/authorize", dependencies=[Protected])
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


@app.post("/runs/wait", dependencies=[Protected])
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


def _pending_interrupt(snapshot) -> bool:
    return any(getattr(t, "interrupts", None) for t in (snapshot.tasks or []))


@app.post("/runs/{thread_id}/resume", dependencies=[Protected])
async def run_resume(thread_id: str, decision: ResumeRequest) -> dict:
    """Người duyệt trả lời → đồ thị chạy tiếp đúng từ chỗ đã dừng.

    Thứ tự kiểm, và vì sao:
      1. Thread phải tồn tại và đang ở điểm chờ — resume một thread đã xong là
         lỗi gọi, không phải quyết định.
      2. `by` phải nằm trong `approvers` của hồ sơ gắn với thread. Kiểm ở ĐÂY,
         trong code, chứ không tin vào bên gọi: token API chỉ chứng minh "n8n
         gọi", không chứng minh "CFO đã duyệt".
      3. Cả duyệt lẫn từ chối đều ghi audit — từ chối cũng là quyết định.
    """
    from langgraph.types import Command

    graph = _state["app"]
    cfg = {"configurable": {"thread_id": thread_id}}

    snap = await graph.aget_state(cfg)
    if snap is None or not snap.values:
        raise HTTPException(404, f"Không có quy trình nào với thread_id '{thread_id}'")
    if not _pending_interrupt(snap):
        raise HTTPException(409, f"Thread '{thread_id}' không ở điểm chờ duyệt")

    profile_name = str(snap.values.get("profile") or "engineering")
    approvers = [str(a) for a in (_load_profile(profile_name).get("approvers") or [])]
    if not decision.by or decision.by not in approvers:
        _audit("permission.decision", thread_id=thread_id, profile=profile_name,
               by=decision.by, approved=decision.approved, allowed=False,
               reason="not-an-approver")
        # Nhánh 403 dừng TRƯỚC KHI chạm graph nên human_approval() trong graph.py
        # không bao giờ chạy cho lượt này — không có dòng này thì một yêu cầu bị
        # từ chối vì sai người không để lại dấu vết bền nào (chỉ có dòng
        # permission.decision ephemeral trên stdout ở trên). Ghi vào trajectory
        # (fail-soft, xem trajectory._append) để bền qua restart/redeploy như
        # mọi quyết định hợp lệ khác.
        trajectory.permission_denied(thread_id, profile=profile_name,
                                      by=decision.by, reason="not-an-approver")
        raise HTTPException(
            403,
            f"'{decision.by or '(trống)'}' không nằm trong danh sách người duyệt "
            f"của hồ sơ '{profile_name}'",
        )

    _audit("permission.decision", thread_id=thread_id, profile=profile_name,
           by=decision.by, approved=decision.approved, allowed=True, note=decision.note)
    await graph.ainvoke(Command(resume=decision.model_dump()), cfg)
    snap = await graph.aget_state(cfg)
    return {"thread_id": thread_id, **_summarize(snap)}


# ---------------------------------------------------------------------------
# Chỉ số vận hành — bốn chỉ số ở mục 3.8 của tài liệu tham chiếu
# ---------------------------------------------------------------------------
@app.get("/metrics", dependencies=[Protected])
async def metrics(days: int = 30) -> dict:
    """Đọc vết chạy và trả bốn chỉ số. Không phải Prometheus.

    Cố ý KHÔNG mở endpoint này cho mọi người: vết chạy chứa mã công việc, tên
    người duyệt và tên file có lỗi. Đó là dữ liệu nội bộ, không phải số liệu
    sức khoẻ công khai. Ai cần dashboard thì gọi kèm token như n8n.

    Trần 365 ngày để một tham số `days` lớn không biến endpoint này thành cách
    làm cạn I/O của cả container.
    """
    from .metrics import collect

    return collect(days=max(1, min(int(days), 365)))


@app.get("/runs/{thread_id}", dependencies=[Protected])
async def run_state(thread_id: str) -> dict:
    graph = _state["app"]
    snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    if snap is None or not snap.values:
        raise HTTPException(404, f"Không có quy trình nào với thread_id '{thread_id}'")
    return {"thread_id": thread_id, **_summarize(snap)}
