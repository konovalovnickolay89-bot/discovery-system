"""Board factories: blank (default) and optional demo seed for local dev only."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    Board,
    BoardMeta,
    BoardStatus,
    BriefingSection,
    Freshness,
    ItemSource,
    LearningItem,
    LearningSection,
    Level,
    MachineSection,
    MediaSection,
    PlayState,
    RecipeSpine,
    TodayItem,
    TodaySection,
    Track,
)


def build_blank_board(*, revision: int = 1, host_label: str = "casual-board") -> Board:
    """Valid empty board — no demo content. Safe for production Start fresh."""
    now = datetime.now(timezone.utc)
    return Board(
        meta=BoardMeta(
            revision=max(1, revision),
            generated_at=now,
            updated_at=now,
            host_label=host_label,
            status=BoardStatus(label="ok · quiet", warnings=0, freshness=Freshness.fresh),
        ),
        today=TodaySection(
            items=[],
            empty_footer="empty — add routines, reminders, captures",
            freshness=Freshness.fresh,
        ),
        media=MediaSection(
            state=PlayState.idle,
            current=None,
            queue=[],
            cassette=True,
            volume=55,
            playlist_label="",
            playlist_url="",
            speaker="—",
            player="mpv",
            fetcher="ytdl",
            cassette_engine="ffmpeg cassette",
            cassette_profile="",
            cassette_repo="",
            path_label="ytdl → mpv → out",
            freshness=Freshness.unknown,
            note="idle — no track; host transport not claimed verified",
        ),
        learning=LearningSection(
            pool=[],
            window_size=5,
            ring=1,
            topics_label="",
            advance_ms=20_000,
            freshness=Freshness.fresh,
        ),
        briefing=BriefingSection(
            pins=[],
            ring=[],
            ring_index=0,
            ring_n=1,
            sources_label="",
            advance_ms=5_000,
            freshness=Freshness.fresh,
        ),
        machine=MachineSection(
            host="awaiting-debian",
            disk_pct=0.0,
            free_gib=0.0,
            failed_units=0,
            net="wired",
            apt_updates=0,
            freshness=Freshness.unknown,
            reported_at=None,
            detail="awaiting a real Debian report (bridge/client)",
        ).with_health(),
    )


def build_seed_board() -> Board:
    """Demo chef + systems fixtures. Local development only — never Start fresh."""
    now = datetime.now(timezone.utc)
    recipe = RecipeSpine(
        one="Lemon & herb roast chicken, one tray",
        why="Quiet service night — high yield, low fuss, parents-friendly",
        how="Spatchcock · zest under skin · 210°C / 40 min · rest 12",
        roles="Lead: roast / second: greens + jus / runner: carve station",
        mise_1="Birds trussed · zest bowl · thyme oil · salt tray · thermometer",
        cost_portion="£2.40 food · plate £11 · target 68% GP",
        watch="Thigh joint probe 74°C · don't over-brown zest · hold carve warm",
        allergens="None intrinsic · check bread crumb garnish if added",
        parents="No chilli · soft greens option · carve away from bone if asked",
        service_pass="Half bird + jus spoon · herb oil finish · lemon cheek on rim",
    )

    today = TodaySection(
        items=[
            TodayItem(
                id="t-open",
                text="Open: walk-in temps, blast chill log, handwash stations",
                kind="routine",
                tags=["routine"],
                source=ItemSource.seed,
                created_at=now,
            ),
            TodayItem(
                id="t-allergen",
                text="11:30 — confirm allergen matrix print for lunch service",
                kind="reminder",
                tags=["reminder", "allergen"],
                level=Level.warn,
                source=ItemSource.seed,
                created_at=now,
            ),
            TodayItem(
                id="t-capture",
                text="Capture: try brown-butter sage on gnocchi next soft open",
                kind="capture",
                tags=["capture"],
                source=ItemSource.seed,
                created_at=now,
            ),
            TodayItem(
                id="t-recipe",
                text="Recipe pin · lemon & herb roast chicken",
                kind="recipe",
                tags=["recipe"],
                recipe=recipe,
                source=ItemSource.seed,
                created_at=now,
            ),
        ],
        freshness=Freshness.fresh,
    )

    media = MediaSection(
        state=PlayState.idle,
        current=Track(
            id="m0",
            title="Late Ferry Home",
            artist="Quiet Harbour",
            yt_id="demo0",
            duration_s=312,
        ),
        queue=[
            Track(id="m1", title="Cassette Dust", artist="Tape Room", duration_s=248),
            Track(id="m2", title="Kitchen After Close", artist="Line Down", duration_s=401),
            Track(id="m3", title="Soft Grid Rain", artist="Signal Low", duration_s=276),
            Track(id="m4", title="Sunday Prep", artist="Mise en Place", duration_s=334),
        ],
        cassette=True,
        volume=55,
        freshness=Freshness.unknown,
        note="mirror only — real transport on Debian client",
    )

    learning = LearningSection(
        pool=[
            LearningItem(
                id="l1",
                topic="allergen-matrix",
                primary="14 major allergens must be presentable from the pass without guessing.",
                detail="Walk the matrix at open. Mark dish changes in red pen. Never improvise mid-service.",
                tags=["allergen-matrix", "pass"],
            ),
            LearningItem(
                id="l2",
                topic="service-rescue",
                primary="When a table goes quiet-angry: acknowledge, own one fix, give a time, deliver.",
                detail="Script once, close the loop yourself. Manager only if guest asks or fix fails.",
                tags=["service-rescue", "front"],
            ),
            LearningItem(
                id="l3",
                topic="line-opening",
                primary="Line open is a checklist: temps, stock, tools, taste, tickets.",
                detail="Only then call line open to the floor. First ticket is a systems test.",
                tags=["line-opening", "open"],
            ),
        ],
        freshness=Freshness.fresh,
    )

    from .models import BriefingItem

    briefing = BriefingSection(
        pins=[
            BriefingItem(
                id="p1",
                title="Demo pin — not for production",
                url="https://example.com",
                source="x",
            ),
        ],
        ring=[
            BriefingItem(
                id="r1",
                title="Demo ring item — not for production",
                url="https://example.com",
                source="hn",
                points=1,
                comments=0,
            ),
        ],
        freshness=Freshness.fresh,
    )

    machine = MachineSection(
        host="debian-minimal",
        disk_pct=42.0,
        free_gib=118.4,
        failed_units=0,
        net="wired",
        apt_updates=3,
        freshness=Freshness.stale,
        reported_at=None,
        detail="demo seed machine — not a live report",
    ).with_health()

    return Board(
        meta=BoardMeta(
            revision=1,
            generated_at=now,
            updated_at=now,
            host_label="casual-board",
            status=BoardStatus(label="ok · quiet", warnings=0, freshness=Freshness.fresh),
        ),
        today=today,
        media=media,
        learning=learning,
        briefing=briefing,
        machine=machine,
    )
