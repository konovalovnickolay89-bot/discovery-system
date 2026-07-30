"""Replaceable seed board — chef + Debian systems workflow."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    Board,
    BoardMeta,
    BoardStatus,
    BriefingItem,
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


def build_seed_board() -> Board:
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
            LearningItem(
                id="l4",
                topic="allergen-matrix",
                primary="Cross-contact is the silent fail: shared oil, same tongs, unlabelled tubs.",
                detail="Separate utensils. Label every mise tub. Second-check new specials.",
                tags=["allergen-matrix", "mise"],
            ),
            LearningItem(
                id="l5",
                topic="service-rescue",
                primary="86'd mid-service: strike the board, tell floor once, offer equal-path sub.",
                detail="Same allergen profile if possible, same price band, write sub on docket.",
                tags=["service-rescue", "board"],
            ),
            LearningItem(
                id="l6",
                topic="line-opening",
                primary="First ticket of the day is a fire drill, not a warm-up plate.",
                detail="Time each hop: print → read → cook → pass → runner. Fix friction before rush.",
                tags=["line-opening", "tickets"],
            ),
        ],
        freshness=Freshness.fresh,
    )

    briefing = BriefingSection(
        pins=[
            BriefingItem(
                id="p1",
                title="Morning light on the Pembrokeshire coast path — still empty at 7am",
                url="https://x.com/explore",
                source="x",
            ),
            BriefingItem(
                id="p2",
                title="Brief note on sleep debt and reaction time — useful for late service weeks",
                url="https://x.com/explore",
                source="x",
            ),
            BriefingItem(
                id="p3",
                title="A small delight: sourdough that finally holds its ear after 40 tries",
                url="https://x.com/explore",
                source="x",
            ),
        ],
        ring=[
            BriefingItem(
                id="r1",
                title="Show HN: offline-first kitchen ticket rail in ~400 lines of C",
                url="https://news.ycombinator.com",
                source="hn",
                points=214,
                comments=89,
            ),
            BriefingItem(
                id="r2",
                title="Quiet thread on keeping a home lab boring on purpose",
                url="https://x.com/explore",
                source="x",
            ),
            BriefingItem(
                id="r3",
                title="Ask HN: personal ops board without it becoming a second job?",
                url="https://news.ycombinator.com",
                source="hn",
                points=156,
                comments=112,
            ),
            BriefingItem(
                id="r4",
                title="Cassette deck maintenance checklist — oddly satisfying",
                url="https://x.com/explore",
                source="x",
            ),
            BriefingItem(
                id="r5",
                title="HN: reading apt and systemd status without the noise",
                url="https://news.ycombinator.com",
                source="hn",
                points=98,
                comments=41,
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
        detail="awaiting debian-client report",
    ).with_health()

    warnings = sum(1 for i in today.items if i.level == Level.warn)
    if machine.warn:
        warnings += 1
    status = (
        BoardStatus(
            label=f"worth a look — {warnings} warnings",
            warnings=warnings,
            freshness=Freshness.fresh,
        )
        if warnings
        else BoardStatus(label="ok · quiet", warnings=0, freshness=Freshness.fresh)
    )

    return Board(
        meta=BoardMeta(
            revision=1,
            generated_at=now,
            updated_at=now,
            host_label="casual-board",
            status=status,
        ),
        today=today,
        media=media,
        learning=learning,
        briefing=briefing,
        machine=machine,
    )
