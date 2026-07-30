"""Casual Board authoritative API.

Web UI on grok.me is public (CORS-locked). Owner/bridge secrets never go to the browser.
Host-facing work is queued for the Debian outbound bridge — not executed on approval.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pydantic
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from . import jobs as job_queue
from .agents import capture_with_ai, capture_without_ai
from .auth import auth_mode, optional_owner, require_bridge, require_owner
from .commands import approve_action, execute_command
from .config import GROK_ME_WEB_ORIGIN, get_settings, validate_or_exit
from .logging_config import setup_logging
from .models import (
    ActionRecord,
    ApprovalRequest,
    Board,
    BridgeJob,
    BridgeJobLeaseResponse,
    BridgeJobResultRequest,
    CaptureRequest,
    CaptureResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    CommandName,
    CommandRequest,
    CommandResponse,
    HealthResponse,
    ItemSource,
    StreamEvent,
    TodayItem,
)
from .store import get_store

log = logging.getLogger("casual_board.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = validate_or_exit()
    setup_logging(settings.log_level)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    board = get_store().get()
    log.info(
        "startup version=%s env=%s revision=%s auth=%s ai=%s cors=%s",
        __version__,
        settings.app_env,
        board.meta.revision,
        auth_mode(),
        settings.resolved_ai_provider(),
        settings.cors_origin_list,
    )
    yield
    log.info("shutdown")


app = FastAPI(
    title="Casual Board API",
    version=__version__,
    description="Authoritative board. Host work via Debian bridge job queue.",
    lifespan=lifespan,
)

_settings = get_settings()
if _settings.trusted_host_list:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_settings.trusted_host_list)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin"],
    expose_headers=["X-Board-Revision"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    try:
        response.headers["X-Board-Revision"] = str(get_store().get().meta.revision)
    except Exception:  # noqa: BLE001
        pass
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _now() -> datetime:
    return datetime.now(timezone.utc)


@app.get("/health", response_model=HealthResponse, tags=["ops"])
@app.get("/v1/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Public liveness — no secrets."""
    settings = get_settings()
    board = get_store().get()
    try:
        import pydantic_ai  # noqa: F401

        pai = True
    except Exception:  # noqa: BLE001
        pai = False
    return HealthResponse(
        ok=True,
        version=__version__,
        env=settings.app_env,
        revision=board.meta.revision,
        auth_mode=auth_mode(),  # type: ignore[arg-type]
        pydantic=pydantic.__version__,
        pydantic_ai_available=pai,
        ai_provider=settings.resolved_ai_provider(),
        data_dir=str(settings.data_dir.resolve()),
        time=_now(),
    )


@app.get("/v1/board", response_model=Board, tags=["board"])
def get_board() -> Board:
    """Public board snapshot (CORS-restricted in production). No browser token."""
    return get_store().get()


@app.get("/v1/board/stream", tags=["board"])
async def board_sse():
    store = get_store()
    q = store.subscribe_async()

    async def gen():
        try:
            board = store.get()
            yield f"data: {StreamEvent(type='snapshot', revision=board.meta.revision, at=_now(), board=board).model_dump_json()}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {event.model_dump_json()}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {StreamEvent(type='ping', at=_now(), revision=store.get().meta.revision).model_dump_json()}\n\n"
        finally:
            store.unsubscribe_async(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.websocket("/v1/board/ws")
async def board_ws(websocket: WebSocket):
    """Public live feed. No token query params (never put CASUAL_BOARD_TOKEN in browsers)."""
    settings = get_settings()
    origin = websocket.headers.get("origin")
    if origin and settings.is_production:
        if origin.rstrip("/") not in set(settings.cors_origin_list):
            await websocket.close(code=4403)
            return
    await websocket.accept()
    store = get_store()
    q = store.subscribe_async()
    try:
        board = store.get()
        await websocket.send_text(
            StreamEvent(
                type="snapshot", revision=board.meta.revision, at=_now(), board=board
            ).model_dump_json()
        )
        while True:
            get_ev = asyncio.create_task(q.get())
            get_msg = asyncio.create_task(websocket.receive_text())
            done, pending = await asyncio.wait(
                {get_ev, get_msg}, return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
            if get_ev in done:
                await websocket.send_text(get_ev.result().model_dump_json())
            if get_msg in done:
                raw = get_msg.result()
                if raw.strip() in {"ping", '{"type":"ping"}'}:
                    await websocket.send_text(
                        StreamEvent(
                            type="ping", at=_now(), revision=store.get().meta.revision
                        ).model_dump_json()
                    )
    except WebSocketDisconnect:
        pass
    finally:
        store.unsubscribe_async(q)


@app.post("/v1/captures", response_model=CaptureResponse, tags=["board"])
def create_capture(body: CaptureRequest) -> CaptureResponse:
    """Public capture → server-side board. AI optional; used_ai only for live providers."""
    store = get_store()
    settings = get_settings()
    use_ai = body.use_ai and settings.enable_pydantic_ai
    if use_ai:
        draft, used, provider = capture_with_ai(body.note)
    else:
        draft, used, provider = capture_without_ai(body.note), False, "none"
    item = TodayItem(
        text=f"{draft.title} — {draft.body}",
        kind="capture",
        tags=draft.tags,
        level=draft.level,
        source=ItemSource.capture,
        created_at=_now(),
        detail=draft.body,
    )
    board = store.get()
    items = list(board.today.items) + [item]
    board = store.set(
        board.model_copy(
            update={"today": board.today.model_copy(update={"items": items})}
        ),
        detail="capture:web",
    )
    return CaptureResponse(
        draft=draft, item=item, board=board, used_ai=used, ai_provider=provider
    )


@app.post("/v1/commands", response_model=CommandResponse, tags=["commands"])
def post_command(
    body: CommandRequest,
    actor: str = Depends(optional_owner),
) -> CommandResponse:
    """Server-side cmds run here; host-facing cmds are queued for the Debian bridge."""
    if body.actor in {"anonymous", ""}:
        body = body.model_copy(update={"actor": actor})
    return execute_command(body)


@app.get("/v1/actions/{action_id}", response_model=ActionRecord, tags=["commands"])
def get_action(action_id: str) -> ActionRecord:
    rec = get_store().get_action(action_id)
    if not rec:
        # try job mirror
        jid = action_id if action_id.startswith("job-") else f"job-{action_id.removeprefix('act-')}"
        job = job_queue.get_job(jid)
        if job:
            from .commands import _action_from_job

            return _action_from_job(job)
        raise HTTPException(status_code=404, detail="action not found")
    return rec


@app.post(
    "/v1/actions/{action_id}/approval",
    response_model=CommandResponse,
    tags=["commands"],
)
def post_approval(
    action_id: str,
    body: ApprovalRequest,
    actor: str = Depends(require_owner),
) -> CommandResponse:
    """Approve bridge job → queued. Does NOT execute host actions in FastAPI."""
    return approve_action(action_id, body.approve, body.note, actor=actor)


# ── Bridge outbound API ────────────────────────────────────────────────


@app.get("/v1/bridge/jobs/lease", response_model=BridgeJobLeaseResponse, tags=["bridge"])
def bridge_lease(
    worker_id: str = Query(default="debian-bridge"),
    timeout_s: float = Query(default=25.0, ge=0.5, le=60.0),
    _bridge: str = Depends(require_bridge),
) -> BridgeJobLeaseResponse:
    """Long-poll: Debian bridge calls this outbound. Returns one leased job or empty."""
    return job_queue.long_poll_lease(worker_id=worker_id, timeout_s=timeout_s)


@app.post("/v1/bridge/jobs/result", response_model=BridgeJob, tags=["bridge"])
def bridge_result(
    body: BridgeJobResultRequest,
    _bridge: str = Depends(require_bridge),
) -> BridgeJob:
    """Signed result from Debian after local executor hook (Hermes stub until verified)."""
    return job_queue.complete_job(body)


@app.get("/v1/bridge/jobs/{job_id}", response_model=BridgeJob, tags=["bridge"])
def bridge_get_job(job_id: str, _bridge: str = Depends(require_bridge)) -> BridgeJob:
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/v1/chat", response_model=ChatMessageResponse, tags=["chat"])
def chat_panel(body: ChatMessageRequest) -> ChatMessageResponse:
    """Hermes/Linux-Wiki panel on the web — maps to board cmds or queues host work. No shell."""
    text = body.message.strip().lower()
    if text in {"status", "?", "help"} or text == "status":
        res = execute_command(
            CommandRequest(command=CommandName.status, source=body.source, actor="web-chat")
        )
        return ChatMessageResponse(
            reply=f"Board: {res.board.meta.status.label if res.board else 'ok'}",
            suggested_commands=[CommandName.status],
            action=res.action,
            board=res.board,
        )
    if text.startswith("capture ") or text.startswith("note "):
        note = body.message.split(" ", 1)[1]
        res = execute_command(
            CommandRequest(
                command=CommandName.capture,
                payload={"note": note},
                source=body.source,
                actor="web-chat",
            )
        )
        return ChatMessageResponse(
            reply=res.action.message or "captured",
            action=res.action,
            board=res.board,
        )
    if text.startswith("add ") or text.startswith("remind"):
        payload_text = body.message.split(" ", 1)[1] if " " in body.message else body.message
        res = execute_command(
            CommandRequest(
                command=CommandName.add_today,
                payload={"text": payload_text},
                source=body.source,
                actor="web-chat",
            )
        )
        return ChatMessageResponse(
            reply=res.action.message,
            action=res.action,
            board=res.board,
        )
    if "machine" in text or "disk" in text:
        # queue host-facing job (needs approval)
        res = execute_command(
            CommandRequest(
                command=CommandName.set_machine,
                payload={},
                source=body.source,
                actor="web-chat",
                route="bridge",
            )
        )
        return ChatMessageResponse(
            reply=(
                f"Queued host job {res.job.id if res.job else '?'} "
                f"({res.action.status.value}) — Debian bridge must lease it. "
                "Not executed on this server."
            ),
            action=res.action,
            job=res.job,
            board=res.board,
            suggested_commands=[CommandName.set_machine],
        )
    return ChatMessageResponse(
        reply=(
            "Allowlisted only: status · capture <note> · add/remind <text> · "
            "machine (queues Debian job). No shell. mpv/Hermes not claimed verified."
        ),
        board=get_store().get(),
    )


@app.post("/v1/admin/reset", response_model=Board, tags=["ops"])
def admin_reset(_actor: str = Depends(require_owner)) -> Board:
    return get_store().reset()


def run() -> None:
    import uvicorn

    s = validate_or_exit()
    uvicorn.run(
        "app.main:app",
        host=s.host,
        port=s.port,
        reload=False,
        log_level=s.log_level.lower(),
        proxy_headers=s.trust_proxy,
        forwarded_allow_ips="*" if s.trust_proxy else "127.0.0.1",
    )


if __name__ == "__main__":
    run()
