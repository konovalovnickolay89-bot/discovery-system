"""SQLite persistence for sessions metadata and bridge jobs."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None
_path: Path | None = None


def connect(db_path: Path) -> sqlite3.Connection:
    global _conn, _path
    with _lock:
        if _conn is not None and _path == db_path:
            return _conn
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _migrate(conn)
        _conn = conn
        _path = db_path
        return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS bridge_jobs (
            id TEXT PRIMARY KEY,
            command TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            actor TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'web',
            client_id TEXT,
            message TEXT NOT NULL DEFAULT '',
            result_json TEXT,
            leased_by TEXT,
            lease_nonce TEXT,
            lease_expires_at TEXT,
            board_revision INTEGER,
            audit_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON bridge_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_created ON bridge_jobs(created_at);

        CREATE TABLE IF NOT EXISTS used_nonces (
            nonce TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            used_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def close() -> None:
    global _conn, _path
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
        _path = None


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def loads(raw: str | None, default: Any = None) -> Any:
    if raw is None or raw == "":
        return default if default is not None else {}
    return json.loads(raw)
