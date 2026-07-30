"""Pydantic v2 domain models — source of truth for board + API contracts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# ── Shared enums ───────────────────────────────────────────────────────


class Level(str, Enum):
    info = "info"
    warn = "warn"
    highlight = "highlight"
    dim = "dim"


class Freshness(str, Enum):
    fresh = "fresh"
    stale = "stale"
    unknown = "unknown"


class ItemSource(str, Enum):
    seed = "seed"
    web = "web"
    cli = "cli"
    hermes = "hermes"
    bridge = "bridge"
    system = "system"
    capture = "capture"


# ── Today ──────────────────────────────────────────────────────────────


class RecipeSpine(BaseModel):
    one: str
    why: str
    how: str
    roles: str
    mise_1: str
    cost_portion: str
    watch: str
    allergens: str
    parents: str
    service_pass: str


class TodayItem(BaseModel):
    id: str = Field(default_factory=lambda: f"t-{uuid4().hex[:10]}")
    text: str
    level: Level = Level.info
    tags: list[str] = Field(default_factory=list)
    url: str | None = None
    detail: str | None = None
    kind: Literal["routine", "reminder", "capture", "recipe"] = "routine"
    source: ItemSource = ItemSource.seed
    recipe: RecipeSpine | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None


class TodaySection(BaseModel):
    items: list[TodayItem] = Field(default_factory=list)
    empty_footer: str = "routine.json is empty — add your day's shape"
    freshness: Freshness = Freshness.fresh


# ── Media ──────────────────────────────────────────────────────────────


class PlayState(str, Enum):
    idle = "idle"
    playing = "playing"
    paused = "paused"


class Track(BaseModel):
    id: str
    title: str
    artist: str = "various"
    yt_id: str | None = None
    duration_s: int | None = None
    url: str | None = None


class MediaSection(BaseModel):
    """Host media mirror. Real mpv/ytdl/cassette stay on Debian."""

    state: PlayState = PlayState.idle
    current: Track | None = None
    queue: list[Track] = Field(default_factory=list)
    cassette: bool = True
    volume: int = Field(default=55, ge=0, le=100)
    playlist_label: str = "CHILLOUT MUSIC 2026"
    playlist_url: str = "https://www.youtube.com/playlist?list=PLchillout2026"
    speaker: str = "speaker up"
    player: str = "mpv"
    fetcher: str = "ytdl"
    cassette_engine: str = "ffmpeg cassette"
    cassette_profile: str = "chrome-type-ii"
    cassette_repo: str = "AARomanov1985/Audio-Cassette-Simulation"
    path_label: str = "ytdl → mpv → ffmpeg cassette → out"
    freshness: Freshness = Freshness.unknown
    note: str | None = None


# ── Learning ───────────────────────────────────────────────────────────


class LearningItem(BaseModel):
    id: str = Field(default_factory=lambda: f"l-{uuid4().hex[:10]}")
    topic: str
    primary: str
    detail: str
    tags: list[str] = Field(default_factory=list)
    level: Level = Level.info
    source: ItemSource = ItemSource.seed
    url: str | None = None


class LearningSection(BaseModel):
    pool: list[LearningItem] = Field(default_factory=list)
    window_size: int = 5
    ring: int = 1
    topics_label: str = "allergen-matrix + service-rescue + line-opening"
    advance_ms: int = 20_000
    freshness: Freshness = Freshness.fresh


# ── Briefing ───────────────────────────────────────────────────────────


class BriefingItem(BaseModel):
    id: str = Field(default_factory=lambda: f"b-{uuid4().hex[:10]}")
    title: str
    url: str
    source_tag: Literal["hn", "x"] = Field(alias="source", default="x")
    points: int | None = None
    comments: int | None = None
    level: Level = Level.info
    detail: str | None = None
    item_source: ItemSource = ItemSource.seed

    model_config = {"populate_by_name": True}

    @field_validator("url")
    @classmethod
    def url_http(cls, v: str) -> str:
        if not v.startswith("http"):
            raise ValueError("url must be absolute http(s)")
        return v


class BriefingSection(BaseModel):
    pins: list[BriefingItem] = Field(default_factory=list, max_length=3)
    ring: list[BriefingItem] = Field(default_factory=list)
    ring_index: int = 0
    ring_n: int = 1
    sources_label: str = "x + hn"
    advance_ms: int = 5_000
    freshness: Freshness = Freshness.fresh


# ── Machine ────────────────────────────────────────────────────────────


class MachineSection(BaseModel):
    host: str = "debian-minimal"
    disk_pct: float = Field(default=0, ge=0, le=100)
    free_gib: float = 0
    failed_units: int = 0
    net: Literal["wired", "wifi", "down"] = "wired"
    apt_updates: int = 0
    warn: bool = False
    detail: str | None = None
    freshness: Freshness = Freshness.unknown
    reported_at: datetime | None = None

    def with_health(self) -> MachineSection:
        unhealthy = (
            self.disk_pct >= 90
            or self.failed_units > 0
            or self.net == "down"
            or self.apt_updates > 50
        )
        return self.model_copy(update={"warn": unhealthy})


# ── Board ──────────────────────────────────────────────────────────────


class BoardStatus(BaseModel):
    label: str = "ok · quiet"
    warnings: int = 0
    freshness: Freshness = Freshness.fresh


class BoardMeta(BaseModel):
    revision: int = 1
    generated_at: datetime
    updated_at: datetime
    host_label: str = "casual-board"
    status: BoardStatus = Field(default_factory=BoardStatus)


class Board(BaseModel):
    meta: BoardMeta
    today: TodaySection
    media: MediaSection
    learning: LearningSection
    briefing: BriefingSection
    machine: MachineSection


# ── API envelopes ──────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "casual-board"
    version: str = "0.1.0"
    env: str = "development"
    revision: int = 0
    auth_mode: Literal["token", "open-dev"] = "open-dev"
    pydantic: str
    pydantic_ai_available: bool = True
    data_dir: str = ""
    time: datetime


class ErrorBody(BaseModel):
    detail: str
    code: str = "error"
    fields: dict[str, Any] | None = None


class CaptureRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    source: ItemSource = ItemSource.web
    use_ai: bool = True


class CaptureDraft(BaseModel):
    title: str
    body: str
    tags: list[str] = Field(default_factory=list)
    level: Level = Level.info
    suggested_when: str = "today"


class CaptureResponse(BaseModel):
    draft: CaptureDraft
    item: TodayItem
    board: Board
    used_ai: bool = False


class CommandName(str, Enum):
    status = "status"
    capture = "capture"
    add_today = "add_today"
    remove_today = "remove_today"
    set_media = "set_media"
    set_machine = "set_machine"
    media_play = "media_play"
    media_pause = "media_pause"
    media_next = "media_next"
    media_stop = "media_stop"
    media_cassette_on = "media_cassette_on"
    media_cassette_off = "media_cassette_off"
    media_volume = "media_volume"


# Tight allowlist for debian-bridge / Hermes (subset)
BRIDGE_ALLOWLIST: frozenset[str] = frozenset(
    {
        CommandName.status.value,
        CommandName.capture.value,
        CommandName.add_today.value,
        CommandName.remove_today.value,
        CommandName.set_media.value,
        CommandName.set_machine.value,
    }
)

SYSTEM_CHANGING: frozenset[str] = frozenset(
    {
        CommandName.set_machine.value,
        CommandName.set_media.value,
        CommandName.remove_today.value,
    }
)


class CommandRequest(BaseModel):
    command: CommandName
    payload: dict[str, Any] = Field(default_factory=dict)
    source: ItemSource = ItemSource.web
    actor: str = "anonymous"
    require_approval: bool = False
    client_id: str | None = None


class ActionStatus(str, Enum):
    accepted = "accepted"
    pending_approval = "pending_approval"
    running = "running"
    completed = "completed"
    rejected = "rejected"
    failed = "failed"


class ActionRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"act-{uuid4().hex[:12]}")
    command: CommandName
    status: ActionStatus
    source: ItemSource
    actor: str
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    message: str = ""
    created_at: datetime
    updated_at: datetime
    board_revision: int | None = None
    audit: dict[str, Any] = Field(default_factory=dict)


class CommandResponse(BaseModel):
    action: ActionRecord
    board: Board | None = None


class ApprovalRequest(BaseModel):
    approve: bool = True
    note: str = ""


class StreamEvent(BaseModel):
    type: Literal["snapshot", "revision", "action", "ping", "error"]
    revision: int | None = None
    at: datetime
    board: Board | None = None
    action: ActionRecord | None = None
    detail: str | None = None


class ChatMessageRequest(BaseModel):
    """Linux-Wiki / Hermes chat panel — NOT unrestricted shell."""

    message: str = Field(min_length=1, max_length=2000)
    channel: Literal["hermes", "linux-wiki", "ops"] = "hermes"
    source: ItemSource = ItemSource.web


class ChatMessageResponse(BaseModel):
    ok: bool = True
    reply: str
    suggested_commands: list[CommandName] = Field(default_factory=list)
    action: ActionRecord | None = None
    board: Board | None = None
