"""Apply media transport commands to board state.

On Debian, Hermes or a small host worker can also run real mpv/ytdl after
seeing the same command via WebSocket — this module keeps the board mirror
consistent for phone + CLI.
"""

from __future__ import annotations

from .models import MediaCommand, MediaCommandRequest, MediaCommandResult, MediaSection, PlayState
from . import store


def _path_label(cassette: bool) -> str:
    if cassette:
        return "ytdl → mpv → ffmpeg cassette → out"
    return "ytdl → mpv → out"


def apply_media_command(req: MediaCommandRequest) -> MediaCommandResult:
    board = store.get_board()
    m = board.media
    note = ""

    cmd = req.command

    if cmd == MediaCommand.play:
        if not m.current and m.queue:
            head, *rest = m.queue
            m = m.model_copy(update={"current": head, "queue": rest})
        m = m.model_copy(update={"state": PlayState.playing})
        note = f"mpv play · {m.current.title if m.current else 'empty'}"

    elif cmd == MediaCommand.pause:
        m = m.model_copy(update={"state": PlayState.paused})
        note = "mpv pause"

    elif cmd == MediaCommand.stop:
        m = m.model_copy(update={"state": PlayState.idle})
        note = "mpv stop"

    elif cmd == MediaCommand.next:
        if m.queue:
            head, *rest = m.queue
            prev = m.current
            queue = ([*rest, prev] if prev else rest)
            m = m.model_copy(
                update={
                    "current": head,
                    "queue": queue,
                    "state": PlayState.playing
                    if m.state == PlayState.idle
                    else m.state,
                }
            )
            note = f"mpv playlist-next · {head.title}"
        else:
            note = "ytdl · no next"

    elif cmd == MediaCommand.cassette_on:
        m = m.model_copy(
            update={"cassette": True, "path_label": _path_label(True)}
        )
        note = f"cassette on · {m.cassette_engine} · {m.cassette_profile}"

    elif cmd == MediaCommand.cassette_off:
        m = m.model_copy(
            update={"cassette": False, "path_label": _path_label(False)}
        )
        note = "cassette off · clean mpv path"

    elif cmd == MediaCommand.volume:
        vol = req.volume if req.volume is not None else m.volume
        vol = max(0, min(100, vol))
        m = m.model_copy(update={"volume": vol})
        note = f"mpv volume {vol}"

    board = store.patch_media(m, source=req.source, detail=note)
    return MediaCommandResult(ok=True, command=cmd, media=board.media, note=note)


def apply_media_patch(media: MediaSection, *, source: str) -> MediaSection:
    """Host agent pushes authoritative mpv state after real IPC."""
    board = store.patch_media(media, source=source, detail="host media snapshot")
    return board.media
