"""Adapter boundary for the *existing* local Debian dashboard.

IMPORTANT: Do not edit the live local dashboard JSON sections from this package
yet. Implement a consumer against HostedBoardPort when you are ready to wire
the curses/TUI dashboard to the hosted snapshot.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from .models import BoardSnapshot


class HostedBoardPort(Protocol):
    """Port the existing dashboard can depend on later."""

    def fetch_snapshot(self) -> BoardSnapshot:
        """Return latest hosted (or cached) board snapshot."""
        ...

    def revision(self) -> int:
        ...


class NullLocalDashboardAdapter:
    """Placeholder — does not touch existing local dashboard files."""

    def __init__(self, dashboard_path: str | None = None) -> None:
        self.dashboard_path = dashboard_path
        self._untouched = True

    def apply_snapshot(self, snapshot: BoardSnapshot) -> dict[str, Any]:
        """Future: map BoardSnapshot → local dashboard section DTOs.

        Currently a no-op that only returns a dry-run mapping report.
        """
        return {
            "applied": False,
            "reason": "local dashboard remains untouched by design",
            "dashboard_path": self.dashboard_path,
            "hosted_revision": snapshot.revision,
            "sections_available": [
                "today",
                "media",
                "learning",
                "briefing",
                "machine",
            ],
        }


class SnapshotToLocalMapper(ABC):
    """Implement when ready to merge hosted board into local curses UI models."""

    @abstractmethod
    def map_today(self, section: dict[str, Any]) -> Any: ...

    @abstractmethod
    def map_media(self, section: dict[str, Any]) -> Any: ...

    @abstractmethod
    def map_machine(self, section: dict[str, Any]) -> Any: ...
