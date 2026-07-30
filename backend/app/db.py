"""SQLite persistence — bridge jobs + Cook Studio kitchen tables + evidence registry."""

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

        CREATE TABLE IF NOT EXISTS produce_lots (
            id TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_produce_status ON produce_lots(status);

        CREATE TABLE IF NOT EXISTS ingredients (
            id TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            name TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dishes (
            id TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cook_consultations (
            id TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            mode TEXT NOT NULL,
            task_status TEXT NOT NULL,
            graph_recall_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cook_task ON cook_consultations(task_status);
        CREATE INDEX IF NOT EXISTS idx_cook_gr ON cook_consultations(graph_recall_status);

        CREATE TABLE IF NOT EXISTS graph_recall_jobs (
            id TEXT PRIMARY KEY,
            consultation_id TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            leased_by TEXT,
            lease_nonce TEXT,
            lease_expires_at TEXT,
            result_json TEXT,
            message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gr_status ON graph_recall_jobs(status);

        CREATE TABLE IF NOT EXISTS graph_recall_nonces (
            nonce TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            used_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS canonical_sources (
            id TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            authority_tier INTEGER NOT NULL DEFAULT 5,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_src_active ON canonical_sources(active);
        CREATE INDEX IF NOT EXISTS idx_src_tier ON canonical_sources(authority_tier);

        CREATE TABLE IF NOT EXISTS source_evidence (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            consultation_id TEXT,
            data_json TEXT NOT NULL,
            retrieved_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ev_source ON source_evidence(source_id);
        CREATE INDEX IF NOT EXISTS idx_ev_consult ON source_evidence(consultation_id);

        CREATE TABLE IF NOT EXISTS consultation_evidence (
            consultation_id TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
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


def get_conn() -> sqlite3.Connection:
    from .config import get_settings

    return connect(get_settings().sqlite_path)


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def loads(raw: str | None, default: Any = None) -> Any:
    if raw is None or raw == "":
        return default if default is not None else {}
    return json.loads(raw)
