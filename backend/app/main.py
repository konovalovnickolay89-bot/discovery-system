"""Casual Board API — private board, durable bridge queue, loopback-friendly."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from . import jobs as job_queue
from .agents import capture_with_ai, capture_without_ai
from .auth import require_bridge, require_owner
from .commands import approve_action, execute_command
from .config import GROK_ME_WEB_ORIGIN, get_settings, validate_or_exit
from .db import connect
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
    LoginRequest,
    SessionResponse,
    StreamEvent,
    TodayItem,
)
from .sessions import login_with_password, require_session, verify_session
from .store import get_store

log = logging.getLogger("casual_board.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = validate_or_exit()
    setup_logging(settings.log_level)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connect(settings.sqlite_path)
    get_store().get()
    log.info(
        "startup version=%s env=%s host=%s cors=%s",
        __version__,
        settings.app_env,
        settings.host,
        settings.cors_origin_list,
    )
    yield


app = FastAPI(title="Casual Board API", version=__version__, lifespan=lifespan)
_settings = get_settings()

if _settings.trusted_host_list:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=_settings.trusted_host_list + ["testserver"],
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list if "*" not in _settings.cors_origin_list else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin"],
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Public minimal health — no board data, no paths, no secrets."""
    return HealthResponse(ok=True, service="casual-board", version=__version__, time=_now())


@app.post("/v1/auth/login", response_model=SessionResponse, tags=["auth"])
def auth_login(body: LoginRequest) -> SessionResponse:
    """Exchange UI password for short-lived session. Not owner/bridge token."""
    data = login_with_password(body.password)
    return SessionResponse(**data)


@app.get("/v1/auth/me", tags=["auth"])
def auth_me(session: dict = Depends(require_session)) -> dict:
    return {"sub": session.get("sub"), "scope": session.get("scope"), "exp": session.get("exp")}


@app.get("/v1/board", response_model=Board, tags=["board"])
def get_board(_s: dict = Depends(require_session)) -> Board:
    return get_store().get()


@app.get("/v1/board/stream", tags=["board"])
async def board_sse(_s: dict = Depends(require_session)):
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

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.websocket("/v1/board/ws")
async def board_ws(websocket: WebSocket, access_token: str | None = Query(default=None)):
    """Session via ?access_token= (browser cannot set WS Authorization easily)."""
    settings = get_settings()
    origin = websocket.headers.get("origin")
    if origin and settings.is_production:
        if origin.rstrip("/") not in set(settings.cors_origin_list):
            await websocket.close(code=4403)
            return
    try:
        if settings.auth_required or settings.ui_password.strip():
            if not access_token:
                await websocket.close(code=4401)
                return
            verify_session(access_token)
        await websocket.accept()
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401)
        return

    store = get_store()
    q = store.subscribe_async()
    try:
        board = store.get()
        await websocket.send_text(
            StreamEvent(type="snapshot", revision=board.meta.revision, at=_now(), board=board).model_dump_json()
        )
        while True:
            get_ev = asyncio.create_task(q.get())
            get_msg = asyncio.create_task(websocket.receive_text())
            done, pending = await asyncio.wait({get_ev, get_msg}, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            if get_ev in done:
                await websocket.send_text(get_ev.result().model_dump_json())
            if get_msg in done and get_msg.result().strip() in {"ping", '{"type":"ping"}'}:
                await websocket.send_text(
                    StreamEvent(type="ping", at=_now(), revision=store.get().meta.revision).model_dump_json()
                )
    except WebSocketDisconnect:
        pass
    finally:
        store.unsubscribe_async(q)


@app.post("/v1/captures", response_model=CaptureResponse, tags=["board"])
def create_capture(body: CaptureRequest, _s: dict = Depends(require_session)) -> CaptureResponse:
    store = get_store()
    settings = get_settings()
    if body.use_ai and settings.enable_pydantic_ai:
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
    board = store.set(
        board.model_copy(update={"today": board.today.model_copy(update={"items": list(board.today.items) + [item]})}),
        detail="capture",
    )
    return CaptureResponse(draft=draft, item=item, board=board, used_ai=used, ai_provider=provider)


@app.post("/v1/commands", response_model=CommandResponse, tags=["commands"])
def post_command(body: CommandRequest, session: dict = Depends(require_session)) -> CommandResponse:
    if body.actor in {"anonymous", ""}:
        body = body.model_copy(update={"actor": str(session.get("sub") or "session")})
    return execute_command(body)


@app.get("/v1/actions/{action_id}", response_model=ActionRecord, tags=["commands"])
def get_action(action_id: str, _s: dict = Depends(require_session)) -> ActionRecord:
    rec = get_store().get_action(action_id)
    if rec:
        return rec
    jid = action_id if action_id.startswith("job-") else f"job-{action_id.removeprefix('act-')}"
    job = job_queue.get_job(jid)
    if job:
        from .commands import _action_from_job

        return _action_from_job(job)
    raise HTTPException(status_code=404, detail="action not found")


@app.post("/v1/actions/{action_id}/approval", response_model=CommandResponse, tags=["commands"])
def post_approval(
    action_id: str,
    body: ApprovalRequest,
    actor: str = Depends(require_owner),
) -> CommandResponse:
    return approve_action(action_id, body.approve, body.note, actor=actor)


@app.get("/v1/bridge/jobs/lease", response_model=BridgeJobLeaseResponse, tags=["bridge"])
def bridge_lease(
    worker_id: str = Query(default="debian-bridge"),
    timeout_s: float = Query(default=25.0, ge=0.5, le=60.0),
    _b: str = Depends(require_bridge),
) -> BridgeJobLeaseResponse:
    return job_queue.long_poll_lease(worker_id=worker_id, timeout_s=timeout_s)


@app.post("/v1/bridge/jobs/result", response_model=BridgeJob, tags=["bridge"])
def bridge_result(body: BridgeJobResultRequest, _b: str = Depends(require_bridge)) -> BridgeJob:
    return job_queue.complete_job(body)


@app.get("/v1/bridge/jobs/{job_id}", response_model=BridgeJob, tags=["bridge"])
def bridge_get_job(job_id: str, _b: str = Depends(require_bridge)) -> BridgeJob:
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/v1/chat", response_model=ChatMessageResponse, tags=["chat"])
def chat_panel(body: ChatMessageRequest, session: dict = Depends(require_session)) -> ChatMessageResponse:
    text = body.message.strip().lower()
    actor = str(session.get("sub") or "session")
    if text in {"status", "?", "help"}:
        res = execute_command(CommandRequest(command=CommandName.status, source=body.source, actor=actor))
        return ChatMessageResponse(
            reply=f"Board: {res.board.meta.status.label if res.board else 'ok'}",
            action=res.action,
            board=res.board,
        )
    if text.startswith("capture ") or text.startswith("note "):
        note = body.message.split(" ", 1)[1]
        res = execute_command(
            CommandRequest(command=CommandName.capture, payload={"note": note}, source=body.source, actor=actor)
        )
        return ChatMessageResponse(reply=res.action.message or "captured", action=res.action, board=res.board)
    if text.startswith("add ") or text.startswith("remind"):
        payload_text = body.message.split(" ", 1)[1] if " " in body.message else body.message
        res = execute_command(
            CommandRequest(
                command=CommandName.add_today, payload={"text": payload_text}, source=body.source, actor=actor
            )
        )
        return ChatMessageResponse(reply=res.action.message, action=res.action, board=res.board)
    return ChatMessageResponse(
        reply="Allowlisted: status · capture <note> · add/remind <text>. No shell. Hermes/mpv not verified.",
        board=get_store().get(),
    )


@app.post("/v1/admin/reset", response_model=Board, tags=["ops"])
def admin_reset(_a: str = Depends(require_owner)) -> Board:
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
        forwarded_allow_ips=s.forwarded_allow_ips,
    )


if __name__ == "__main__":
    run()
