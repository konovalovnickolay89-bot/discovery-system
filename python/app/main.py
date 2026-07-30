"""Casual Board API — single source of truth for web, CLI, Hermes, host.

Bidirectional model:
  phone web  ⇄  FastAPI + WebSocket  ⇄  Debian CLI / Hermes / mpv host worker
"""

from __future__ import annotations

from datetime import datetime, timezone

import pydantic
import pydantic_ai
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import store
from .agents import meta_dict, run_capture, run_learning_expand
from .auth import mint_dev_hint, require_admin
from .hermes_actions import handle_hermes
from .media_host import apply_media_command, apply_media_patch
from .models import (
    Board,
    CaptureRequest,
    CaptureResponse,
    HealthResponse,
    HermesRequest,
    HermesResponse,
    LearningExpandRequest,
    LearningExpandResponse,
    LearningItem,
    MediaCommandRequest,
    MediaCommandResult,
    MediaSection,
    TodayItem,
)

app = FastAPI(
    title="Casual Board API",
    version="1.1.0",
    description="Shared board for phone web + Debian CLI + Hermes maintainer agent",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    m = meta_dict()
    snap = store.snapshot_meta()
    return HealthResponse(
        ok=True,
        pydantic=pydantic.__version__,
        pydantic_ai=pydantic_ai.__version__,
        engine=m["engine"],
        seq=int(snap["seq"]),
        data_path=str(snap["data_path"]),
        auth=mint_dev_hint(),
    )


@app.get("/api/board", response_model=Board)
def get_board() -> Board:
    return store.get_board()


@app.post("/api/ai/capture", response_model=CaptureResponse)
def ai_capture(body: CaptureRequest) -> CaptureResponse:
    try:
        draft = run_capture(body.note)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"PydanticAI capture failed: {e}") from e

    cur = store.get_board()
    item = TodayItem(
        id=f"cap-{int(datetime.now(timezone.utc).timestamp())}",
        text=f"{draft.title} — {draft.body}",
        kind="capture",
        tags=draft.tags,
        level=draft.level,
    )
    items = list(cur.today.items) + [item]
    board = store.set_board(
        cur.model_copy(update={"today": cur.today.model_copy(update={"items": items})}),
        source=body.source or "web",
        kind="capture",
        detail=draft.title,
    )
    return CaptureResponse(draft=draft, meta=meta_dict(), board=board)  # type: ignore[arg-type]


@app.post("/api/ai/learning", response_model=LearningExpandResponse)
def ai_learning(body: LearningExpandRequest) -> LearningExpandResponse:
    try:
        expansion = run_learning_expand(body.prompt, body.topic)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"PydanticAI learning failed: {e}") from e

    cur = store.get_board()
    item = LearningItem(
        id=f"learn-{int(datetime.now(timezone.utc).timestamp())}",
        topic=expansion.topic,
        primary=expansion.primary,
        detail=expansion.detail,
        tags=expansion.tags,
    )
    pool = list(cur.learning.pool) + [item]
    board = store.set_board(
        cur.model_copy(
            update={"learning": cur.learning.model_copy(update={"pool": pool})}
        ),
        source=body.source or "web",
        kind="learning",
        detail=expansion.topic,
    )
    return LearningExpandResponse(item=expansion, meta=meta_dict(), board=board)  # type: ignore[arg-type]


@app.post("/api/media/command", response_model=MediaCommandResult)
def media_command(body: MediaCommandRequest) -> MediaCommandResult:
    """Phone/web/CLI transport controls → board mirror (+ host can act via WS)."""
    return apply_media_command(body)


@app.put("/api/media/state", response_model=MediaSection)
def media_state_put(
    body: MediaSection,
    actor: str = Depends(require_admin),
) -> MediaSection:
    """Host worker / Hermes pushes authoritative mpv+ytdl+cassette snapshot."""
    return apply_media_patch(body, source=actor)


@app.post("/api/hermes", response_model=HermesResponse)
def hermes_endpoint(
    body: HermesRequest,
    actor: str = Depends(require_admin),
) -> HermesResponse:
    """Maintainer agent (Hermes on Debian) administers the board."""
    if not body.agent:
        body = body.model_copy(update={"agent": actor})
    return handle_hermes(body)


@app.post("/api/board/reset", response_model=Board)
def reset_board(actor: str = Depends(require_admin)) -> Board:
    return store.reset_board(source=actor)


@app.websocket("/api/ws")
async def board_ws(websocket: WebSocket) -> None:
    """Bidirectional live sync: web phones, CLI watchers, Hermes, host worker."""
    await websocket.accept()
    role = websocket.query_params.get("role", "web")
    name = websocket.query_params.get("name", "anonymous")
    q = store.subscribe_async()
    try:
        # Immediate snapshot
        board = store.get_board()
        await websocket.send_json(
            {
                "type": "snapshot",
                "role": role,
                "name": name,
                "seq": store.seq(),
                "board": board.model_dump(mode="json"),
            }
        )
        while True:
            # Prefer outbound events; also accept inbound media commands from clients
            try:
                # Wait for either client message or store event
                import asyncio

                get_event = asyncio.create_task(q.get())
                get_msg = asyncio.create_task(websocket.receive_json())
                done, pending = await asyncio.wait(
                    {get_event, get_msg},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()

                if get_event in done:
                    event = get_event.result()
                    await websocket.send_json(
                        {
                            "type": "event",
                            "event": event.model_dump(mode="json"),
                        }
                    )
                if get_msg in done:
                    msg = get_msg.result()
                    await _handle_ws_inbound(websocket, msg, role=role, name=name)
            except WebSocketDisconnect:
                raise
            except Exception as e:  # noqa: BLE001
                await websocket.send_json({"type": "error", "detail": str(e)})
    except WebSocketDisconnect:
        pass
    finally:
        store.unsubscribe_async(q)


async def _handle_ws_inbound(
    websocket: WebSocket,
    msg: dict,
    *,
    role: str,
    name: str,
) -> None:
    mtype = msg.get("type")
    source = f"{role}:{name}"

    if mtype == "ping":
        await websocket.send_json({"type": "pong", "seq": store.seq()})
        return

    if mtype == "media_command":
        body = MediaCommandRequest.model_validate(
            {**msg.get("payload", {}), "source": source}
        )
        result = apply_media_command(body)
        await websocket.send_json(
            {"type": "media_result", "result": result.model_dump(mode="json")}
        )
        return

    if mtype == "capture":
        note = str(msg.get("note") or "")
        if not note.strip():
            await websocket.send_json({"type": "error", "detail": "note required"})
            return
        draft = run_capture(note)
        cur = store.get_board()
        item = TodayItem(
            id=f"cap-{int(datetime.now(timezone.utc).timestamp())}",
            text=f"{draft.title} — {draft.body}",
            kind="capture",
            tags=draft.tags,
            level=draft.level,
        )
        items = list(cur.today.items) + [item]
        store.set_board(
            cur.model_copy(update={"today": cur.today.model_copy(update={"items": items})}),
            source=source,
            kind="capture",
            detail=draft.title,
        )
        return

    await websocket.send_json({"type": "error", "detail": f"unknown type {mtype}"})
