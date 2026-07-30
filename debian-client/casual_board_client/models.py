"""Minimal board snapshot types (mirrors backend contracts loosely)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BoardSnapshot(BaseModel):
    """Opaque-enough snapshot for CLI display + local cache."""

    meta: dict[str, Any] = Field(default_factory=dict)
    today: dict[str, Any] = Field(default_factory=dict)
    media: dict[str, Any] = Field(default_factory=dict)
    learning: dict[str, Any] = Field(default_factory=dict)
    briefing: dict[str, Any] = Field(default_factory=dict)
    machine: dict[str, Any] = Field(default_factory=dict)

    @property
    def revision(self) -> int:
        return int(self.meta.get("revision") or 0)

    @property
    def status_label(self) -> str:
        st = self.meta.get("status") or {}
        return str(st.get("label") or "unknown")
