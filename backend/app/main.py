"""Casual Board authoritative API.

Production architecture (discovery-system.grok.me):
  - Web UI publishes to https://discovery-system.grok.me (Nitro/Node on Grok host).
  - This FastAPI process does NOT run on grok.me. Deploy it on a separate
    Python host (recommended free path: your Debian box + Cloudflare Tunnel).
  - Browser sets VITE_API_BASE_URL to that API's public https origin.
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
from .auth import auth_mode, require_token
from .commands import approve_action, execute_command
from .config import GROK_ME_WEB_ORIGIN, get_settings, validate_or_exit
from .logging_config import setup_logging
from .models import (
    ActionRecord,
    ApprovalRequest,
    Board,
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
from .agents import capture_with_ai, capture_without_ai
from .store import get_store

log = logging.getLogger("casual_board.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = validate_or_exit()
    setup_logging(settings.log_level)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    board = get_store().get()
    log.info(
        "startup version=%s env=%s revision=%s auth=%s cors=%s public=%s data_dir=%s",
        __version__,
        settings.app_env,
        board.meta.revision,
        auth_mode(),
        settings.cors_origin_list,
        settings.public_base_url or "(unset)",
        settings.data_dir,
    )
    if settings.is_production:
        log.info("production mode · web origin expected: %s", GROK_ME_WEB_ORIGIN)
    yield
    log.info("shutdown")


app = FastAPI(
    title="Casual Board API",
    version=__version__,
    description=(
        "Authoritative personal board for phone web + Debian CLI consumers. "
        "OpenAPI at /docs. Not hosted on grok.me — see README."
    ),
    lifespan=lifespan,
)

_settings = get_settings()

# Trusted hosts (optional; set CASUAL_BOARD_TRUSTED_HOSTS in production)
if _settings.trusted_host_list:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_settings.trusted_host_list)

# CORS — explicit origins in production (includes discovery-system.grok.me)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin"],
    expose_headers=["X-Board-Revision"],
)


@app.middleware("http")
async def security_and_proxy_headers(request: Request, call_next):
    """Respect reverse-proxy HTTPS and attach useful response headers."""
    settings = get_settings()
    if settings.trust_proxy:
        # Starlette/uvicorn already see X-Forwarded-* when --proxy-headers is on;
        # we record proto for logs / health.
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        request.state.forwarded_proto = proto  # type: ignore[attr-defined]
    response = await call_next(request)
    try:
        response.headers["X-Board-Revision"] = str(get_store().get().meta.revision)
    except Exception:  # noqa: BLE001
        pass
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Help browsers talking from grok.me
    if settings.is_production:
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


def _now() -> datetime:
    return datetime.now(timezone.utc)


@app.get("/health", response_model=HealthResponse, tags=["ops"])
@app.get("/v1/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    settings = get_settings()
    store = get_store()
    board = store.get()
    pydantic_ai_ok = True
    try:
        import pydantic_ai  # noqa: F401
    except Exception:  # noqa: BLE001
        pydantic_ai_ok = False
    return HealthResponse(
        ok=True,
        version=__version__,
        env=settings.app_env,
        revision=board.meta.revision,
        auth_mode=auth_mode(),  # type: ignore[arg-type]
        pydantic=pydantic.__version__,
        pydantic_ai_available=pydantic_ai_ok,
        data_dir=str(settings.data_dir.resolve()),
        time=_now(),
    )


@app.get("/v1/board", response_model=Board, tags=["board"])
def get_board(_actor: str = Depends(require_token)) -> Board:
    """Read current board. Works without any LLM."""
    return get_store().get()


@app.get("/v1/board/stream", tags=["board"])
async def board_sse(_actor: str = Depends(require_token)):
    """Server-Sent Events stream of board revisions (works over HTTPS)."""
    store = get_store()
    q = store.subscribe_async()

    async def gen():
        try:
            board = store.get()
            snap = StreamEvent(
                type="snapshot",
                revision=board.meta.revision,
                at=_now(),
                board=board,
            )
            yield f"data: {snap.model_dump_json()}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {event.model_dump_json()}\n\n"
                except asyncio.TimeoutError:
                    ping = StreamEvent(
                        type="ping", at=_now(), revision=store.get().meta.revision
                    )
                    yield f"data: {ping.model_dump_json()}\n\n"
        finally:
            store.unsubscribe_async(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.websocket("/v1/board/ws")
async def board_ws(websocket: WebSocket, token: str | None = Query(default=None)):
    """WebSocket live board feed. Use wss:// when behind HTTPS proxy."""
    settings = get_settings()
    # Origin check for browser clients (Debian CLI has no Origin)
    origin = websocket.headers.get("origin")
    if origin and settings.is_production:
        allowed = set(settings.cors_origin_list)
        if origin.rstrip("/") not in allowed:
            log.warning("ws origin rejected: %s", origin)
            await websocket.close(code=4403)
            return
    if settings.auth_required:
        if not token or token != settings.api_token:
            await websocket.close(code=4401)
            return
    await websocket.accept()
    store = get_store()
    q = store.subscribe_async()
    try:
        board = store.get()
        await websocket.send_text(
            StreamEvent(
                type="snapshot",
                revision=board.meta.revision,
                at=_now(),
                board=board,
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
                ev = get_ev.result()
                await websocket.send_text(ev.model_dump_json())
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
def create_capture(
    body: CaptureRequest,
    actor: str = Depends(require_token),
) -> CaptureResponse:
    store = get_store()
    settings = get_settings()
    use_ai = body.use_ai and settings.enable_pydantic_ai
    draft, used = (
        capture_with_ai(body.note) if use_ai else (capture_without_ai(body.note), False)
    )
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
        detail=f"capture:{actor}",
    )
    return CaptureResponse(draft=draft, item=item, board=board, used_ai=used)


@app.post("/v1/commands", response_model=CommandResponse, tags=["commands"])
def post_command(
    body: CommandRequest,
    actor: str = Depends(require_token),
) -> CommandResponse:
    if body.actor in {"anonymous", ""}:
        body = body.model_copy(update={"actor": actor})
    return execute_command(body, from_bridge=body.source == ItemSource.bridge)


@app.get("/v1/actions/{action_id}", response_model=ActionRecord, tags=["commands"])
def get_action(action_id: str, _actor: str = Depends(require_token)) -> ActionRecord:
    rec = get_store().get_action(action_id)
    if not rec:
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
    _actor: str = Depends(require_token),
) -> CommandResponse:
    return approve_action(action_id, body.approve, body.note)


@app.post("/v1/chat", response_model=ChatMessageResponse, tags=["chat"])
def chat_panel(
    body: ChatMessageRequest,
    actor: str = Depends(require_token),
) -> ChatMessageResponse:
    """Hermes / Linux-Wiki panel — maps intent to allowlisted commands only."""
    text = body.message.strip().lower()
    suggested: list[CommandName] = []
    reply = (
        "I can run allowlisted board commands only "
        "(status, capture, today, media, machine). No shell."
    )

    if text in {"status", "?", "help"} or "status" in text:
        suggested = [CommandName.status]
        res = execute_command(
            CommandRequest(
                command=CommandName.status,
                source=body.source,
                actor=actor,
            )
        )
        return ChatMessageResponse(
            reply=(
                f"Board: {res.board.meta.status.label if res.board else 'ok'} · "
                f"rev {res.board.meta.revision if res.board else '?'}"
            ),
            suggested_commands=suggested,
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
                actor=actor,
            )
        )
        return ChatMessageResponse(
            reply=res.action.message or "captured",
            suggested_commands=[CommandName.capture],
            action=res.action,
            board=res.board,
        )

    if "add " in text or text.startswith("remind"):
        parts = body.message.split(" ", 1)
        payload_text = parts[1] if len(parts) > 1 else body.message
        res = execute_command(
            CommandRequest(
                command=CommandName.add_today,
                payload={"text": payload_text},
                source=body.source,
                actor=actor,
            )
        )
        return ChatMessageResponse(
            reply=res.action.message,
            suggested_commands=[CommandName.add_today],
            action=res.action,
            board=res.board,
        )

    if "play" in text:
        suggested.append(CommandName.media_play)
    if "pause" in text:
        suggested.append(CommandName.media_pause)
    if "machine" in text or "disk" in text:
        suggested.append(CommandName.set_machine)

    return ChatMessageResponse(
        reply=reply, suggested_commands=suggested, board=get_store().get()
    )


@app.post("/v1/admin/reset", response_model=Board, tags=["ops"])
def admin_reset(_actor: str = Depends(require_token)) -> Board:
    return get_store().reset()


def run() -> None:
    import uvicorn

    s = validate_or_exit()
    # proxy_headers=True so HTTPS/WSS from Cloudflare/Caddy is correct
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
