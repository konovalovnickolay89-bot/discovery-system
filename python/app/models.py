"""Casual Board domain models — validated by Pydantic end-to-end."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Level(str, Enum):
    info = "info"
    warn = "warn"
    highlight = "highlight"
    dim = "dim"


class Tag(str, Enum):
    hn = "hn"
    x = "x"
    capture = "capture"
    yt = "yt"
    idle = "idle"
    recipe = "recipe"
    routine = "routine"
    reminder = "reminder"


# ── Today ──────────────────────────────────────────────────────────────


class RecipeSpine(BaseModel):
    one: str = Field(description="The dish in one line")
    why: str = Field(description="Why cook this today")
    how: str = Field(description="Core method")
    roles: str = Field(description="Who does what on the pass")
    mise_1: str = Field(description="First mise block")
    cost_portion: str = Field(description="Cost per portion")
    watch: str = Field(description="Watch-outs on the line")
    allergens: str = Field(description="Allergen callouts")
    parents: str = Field(description="Parent / guest notes")
    service_pass: str = Field(description="Service / pass notes")


class TodayItem(BaseModel):
    id: str
    text: str
    level: Level = Level.info
    tags: list[Tag] = Field(default_factory=list)
    url: str | None = None
    kind: Literal["routine", "reminder", "capture", "recipe"] = "routine"
    recipe: RecipeSpine | None = None


class TodaySection(BaseModel):
    items: list[TodayItem] = Field(default_factory=list)
    empty_footer: str = "routine.json is empty — add your day's shape"


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


class MediaSection(BaseModel):
    """Host audio path (debian-minimal):

    YouTube playlist → yt-dlp/ytdl → mpv → [optional ffmpeg cassette] → speakers
    """

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


# ── Learning ───────────────────────────────────────────────────────────


class LearningItem(BaseModel):
    id: str
    topic: str
    primary: str = Field(description="Amber primary line; may wrap ~5 lines")
    detail: str = Field(description="Always expanded under the row")
    tags: list[str] = Field(default_factory=list)


class LearningSection(BaseModel):
    pool: list[LearningItem]
    window_size: int = 5
    ring: int = 1
    topics_label: str = "allergen-matrix + service-rescue"
    advance_ms: int = 20_000


# ── Briefing ───────────────────────────────────────────────────────────


class BriefingItem(BaseModel):
    id: str
    title: str
    url: str
    source: Literal["hn", "x"]
    points: int | None = None
    comments: int | None = None
    level: Level = Level.info

    @field_validator("url")
    @classmethod
    def url_nonempty(cls, v: str) -> str:
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


# ── Machine ────────────────────────────────────────────────────────────


class MachineSection(BaseModel):
    host: str = "debian-minimal"
    disk_pct: float = Field(ge=0, le=100)
    free_gib: float
    failed_units: int = 0
    net: Literal["wired", "wifi", "down"] = "wired"
    apt_updates: int = 0
    warn: bool = False

    def with_health(self) -> MachineSection:
        unhealthy = (
            self.disk_pct >= 90
            or self.failed_units > 0
            or self.net == "down"
            or self.apt_updates > 50
        )
        return self.model_copy(update={"warn": unhealthy})


# ── Board + header ─────────────────────────────────────────────────────


class BoardStatus(BaseModel):
    label: str = "ok · quiet"
    warnings: int = 0


class BoardHeader(BaseModel):
    host: str = "debian-minimal"
    updated_at: datetime
    status: BoardStatus


class Board(BaseModel):
    header: BoardHeader
    today: TodaySection
    media: MediaSection
    learning: LearningSection
    briefing: BriefingSection
    machine: MachineSection


# ── Sync / events (CLI ↔ web ↔ Hermes) ─────────────────────────────────


class BoardEvent(BaseModel):
    """Fan-out event after any mutation — WebSocket + Hermes hooks."""

    seq: int
    kind: str
    source: str  # web | cli | hermes | host | admin | system
    detail: str = ""
    at: datetime
    board: Board


class ClientHello(BaseModel):
    role: Literal["web", "cli", "hermes", "host"] = "web"
    name: str = "anonymous"


# ── Host media commands (phone/web → Debian mpv path) ───────────────────


class MediaCommand(str, Enum):
    play = "play"
    pause = "pause"
    next = "next"
    stop = "stop"
    cassette_on = "cassette_on"
    cassette_off = "cassette_off"
    volume = "volume"


class MediaCommandRequest(BaseModel):
    command: MediaCommand
    volume: int | None = Field(default=None, ge=0, le=100)
    source: str = "web"


class MediaCommandResult(BaseModel):
    ok: bool = True
    command: MediaCommand
    media: MediaSection
    note: str = ""


# ── Hermes maintainer agent ─────────────────────────────────────────────


class HermesAction(str, Enum):
    """Actions the Hermes agent on Debian may perform."""

    status = "status"
    reset_board = "reset_board"
    set_machine = "set_machine"
    add_today = "add_today"
    remove_today = "remove_today"
    set_media = "set_media"
    capture = "capture"
    ping = "ping"


class HermesRequest(BaseModel):
    action: HermesAction
    payload: dict[str, Any] = Field(default_factory=dict)
    agent: str = "hermes"


class HermesResponse(BaseModel):
    ok: bool = True
    action: HermesAction
    message: str = ""
    board: Board | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


# ── PydanticAI structured outputs ──────────────────────────────────────


class CaptureDraft(BaseModel):
    """Structured journal capture produced by the PydanticAI agent."""

    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=800)
    tags: list[Tag] = Field(default_factory=lambda: [Tag.capture])
    level: Level = Level.info
    suggested_when: str = Field(
        default="today",
        description="When this capture should surface (today / later / week)",
    )


class LearningExpansion(BaseModel):
    """Agent expands a kitchen SOP into a learning row."""

    topic: str
    primary: str
    detail: str
    tags: list[str] = Field(default_factory=list)


class CaptureRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    source: str = "web"


class LearningExpandRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    topic: str = "service-rescue"
    source: str = "web"


class AiMeta(BaseModel):
    engine: str
    model: str
    validated_by: str = "pydantic"


class CaptureResponse(BaseModel):
    draft: CaptureDraft
    meta: AiMeta
    board: Board | None = None


class LearningExpandResponse(BaseModel):
    item: LearningExpansion
    meta: AiMeta
    board: Board | None = None


class HealthResponse(BaseModel):
    ok: bool = True
    pydantic: str
    pydantic_ai: str
    engine: str
    seq: int = 0
    data_path: str = ""
    auth: dict[str, str] = Field(default_factory=dict)
    roles: list[str] = Field(
        default_factory=lambda: ["web", "cli", "hermes", "host"]
    )
