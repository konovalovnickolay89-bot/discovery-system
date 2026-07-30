"""Authenticated HTTP + reconnecting WebSocket client."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from .cache import SnapshotCache
from .models import BoardSnapshot

DEFAULT_BASE = os.environ.get("CASUAL_BOARD_API_URL", "http://127.0.0.1:8090").rstrip("/")
DEFAULT_TOKEN = os.environ.get("CASUAL_BOARD_TOKEN", "")


class BoardApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        cache: SnapshotCache | None = None,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE).rstrip("/")
        self.token = token if token is not None else DEFAULT_TOKEN
        self.cache = cache or SnapshotCache()

    def _headers(self) -> dict[str, str]:
        h = {"accept": "application/json", "content-type": "application/json"}
        if self.token:
            h["authorization"] = f"Bearer {self.token}"
        return h

    def health(self) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{self.base_url}/health", headers=self._headers())
            r.raise_for_status()
            return r.json()

    def get_board(self) -> BoardSnapshot:
        try:
            with httpx.Client(timeout=20.0) as c:
                r = c.get(f"{self.base_url}/v1/board", headers=self._headers())
                r.raise_for_status()
                snap = BoardSnapshot.model_validate(r.json())
                self.cache.save(snap)
                return snap
        except Exception:
            cached = self.cache.load()
            if cached:
                return cached
            raise

    def capture(self, note: str) -> dict[str, Any]:
        with httpx.Client(timeout=60.0) as c:
            r = c.post(
                f"{self.base_url}/v1/captures",
                headers=self._headers(),
                json={"note": note, "source": "cli"},
            )
            r.raise_for_status()
            data = r.json()
            if data.get("board"):
                self.cache.save(BoardSnapshot.model_validate(data["board"]))
            return data

    def command(self, command: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(
                f"{self.base_url}/v1/commands",
                headers=self._headers(),
                json={
                    "command": command,
                    "payload": payload or {},
                    "source": "cli",
                    "actor": "debian-cli",
                },
            )
            r.raise_for_status()
            data = r.json()
            if data.get("board"):
                self.cache.save(BoardSnapshot.model_validate(data["board"]))
            return data

    async def watch_ws(
        self,
        on_board: Callable[[BoardSnapshot], None],
        *,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Reconnect loop for /v1/board/ws."""
        try:
            import websockets
        except ImportError as e:
            raise RuntimeError("websockets package required for watch") from e

        delay = 1.0
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            url = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
            url = f"{url}/v1/board/ws"
            if self.token:
                url = f"{url}?token={self.token}"
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    delay = 1.0
                    async for raw in ws:
                        if stop.is_set():
                            break
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        board = msg.get("board")
                        if board:
                            snap = BoardSnapshot.model_validate(board)
                            self.cache.save(snap)
                            on_board(snap)
            except Exception:
                if stop.is_set():
                    break
                await asyncio.sleep(delay)
                delay = min(30.0, delay * 1.7)
