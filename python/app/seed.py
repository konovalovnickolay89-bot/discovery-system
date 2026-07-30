"""Seed board data — kitchen SOPs + calm briefing mix."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    Board,
    BoardHeader,
    BoardStatus,
    BriefingItem,
    BriefingSection,
    LearningItem,
    LearningSection,
    Level,
    MachineSection,
    MediaSection,
    PlayState,
    RecipeSpine,
    Tag,
    TodayItem,
    TodaySection,
    Track,
)


def build_board() -> Board:
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
                id="t1",
                text="Open: walk-in temps, blast chill log, handwash stations",
                kind="routine",
                tags=[Tag.routine],
            ),
            TodayItem(
                id="t2",
                text="11:30 — confirm allergen matrix print for lunch service",
                kind="reminder",
                tags=[Tag.reminder],
                level=Level.warn,
            ),
            TodayItem(
                id="t3",
                text="Capture: try brown-butter sage on gnocchi next soft open",
                kind="capture",
                tags=[Tag.capture],
            ),
            TodayItem(
                id="t4",
                text="Recipe pin · lemon & herb roast chicken",
                kind="recipe",
                tags=[Tag.recipe],
                recipe=recipe,
            ),
        ]
    )

    # Host path: YouTube playlist → ytdl → mpv → [ffmpeg cassette] → speakers
    media = MediaSection(
        state=PlayState.idle,
        current=Track(
            id="m0",
            title="Late Ferry Home",
            artist="Quiet Harbour",
            yt_id="dQw4w9WgXcQ",
            duration_s=312,
        ),
        queue=[
            Track(id="m1", title="Cassette Dust", artist="Tape Room", yt_id="yt1", duration_s=248),
            Track(id="m2", title="Kitchen After Close", artist="Line Down", yt_id="yt2", duration_s=401),
            Track(id="m3", title="Soft Grid Rain", artist="Signal Low", yt_id="yt3", duration_s=276),
            Track(id="m4", title="Sunday Prep", artist="Mise en Place", yt_id="yt4", duration_s=334),
            Track(id="m5", title="Blue Hour Pass", artist="Service End", yt_id="yt5", duration_s=298),
        ],
        cassette=True,
        volume=55,
        playlist_label="CHILLOUT MUSIC 2026",
        playlist_url="https://www.youtube.com/playlist?list=PLchillout2026",
        speaker="speaker up",
        player="mpv",
        fetcher="ytdl",
        cassette_engine="ffmpeg cassette",
        cassette_profile="chrome-type-ii",
        cassette_repo="AARomanov1985/Audio-Cassette-Simulation",
        path_label="ytdl → mpv → ffmpeg cassette → out",
    )

    learning_pool = [
        LearningItem(
            id="l1",
            topic="allergen-matrix",
            primary="14 major allergens must be presentable from the pass without guessing — matrix lives on the clip, not in someone's head.",
            detail="Walk the matrix at open: celery, gluten, crustaceans, eggs, fish, lupin, milk, molluscs, mustard, nuts, peanuts, sesame, soya, sulphites. Mark dish changes in red pen before service. If a guest asks mid-service, freeze the plate, check matrix, then speak — never improvise from memory.",
            tags=["allergen-matrix", "pass"],
        ),
        LearningItem(
            id="l2",
            topic="allergen-matrix",
            primary="Cross-contact is the silent fail: shared fryer oil, same tongs on fish and veg, unlabelled deli tubs in the fridge.",
            detail="Separate utensils for allergen-critical plates. Fryer oil used for battered fish is not 'fine for chips' if a guest is fish-allergic. Label every mise tub with allergen codes. Second-check the board when a new special lands.",
            tags=["allergen-matrix", "mise"],
        ),
        LearningItem(
            id="l3",
            topic="service-rescue",
            primary="When a table goes quiet-angry: acknowledge, own one concrete fix, give a time, then deliver — don't over-apologise.",
            detail="Script: 'You're right — that wait is on us. I'm putting a fresh plate on now; eight minutes, and a drink while you wait.' Then close the loop yourself. Manager only if the guest asks or the fix fails. Never blame the kitchen out loud.",
            tags=["service-rescue", "front"],
        ),
        LearningItem(
            id="l4",
            topic="service-rescue",
            primary="86'd mid-service: strike the board, tell floor in one sentence, offer the nearest equal dish with the same protein or diet path.",
            detail="Don't hide 86s. Floor needs the list before the next order fires. Equal-path means: same allergen profile if possible, same price band, same cook time. Write the sub on the docket so the pass doesn't re-cook the dead dish.",
            tags=["service-rescue", "board"],
        ),
        LearningItem(
            id="l5",
            topic="line-opening",
            primary="Line open is a checklist, not a vibe: temps, stock, tools, taste, tickets.",
            detail="Order: (1) fridge/freezer/hot-hold temps logged, (2) stock counts for proteins + sauces, (3) knives + boards clean and staged, (4) taste every sauce and stock, (5) printer/ticket rail clear. Only then call 'line open' to the floor.",
            tags=["line-opening", "open"],
        ),
        LearningItem(
            id="l6",
            topic="line-opening",
            primary="First ticket of the day is a systems test — treat it like a fire drill, not a warm-up plate.",
            detail="Watch ticket print, station read, cook start, pass call, runner pickup. Time each hop. Fix friction before the rush. If the first plate is late, the system is late — not the cook.",
            tags=["line-opening", "tickets"],
        ),
        LearningItem(
            id="l7",
            topic="allergen-matrix",
            primary="Verbal allergen confirmation at the pass: cook repeats guest constraint back before plating.",
            detail="Runner says 'table 12, no gluten, no dairy'. Cook: 'no gluten, no dairy — confirmed'. Only then plate. If the dish can't be made safe, stop and re-route; never 'just pick the croutons off'.",
            tags=["allergen-matrix", "pass"],
        ),
        LearningItem(
            id="l8",
            topic="service-rescue",
            primary="Wrong dish to table: remove fully, re-fire clean, never 'rework' the plate in front of the guest.",
            detail="Full lift-off. Apologise once. Re-fire with a mark on the docket. Comp only if the wait is long or the guest asks — don't train the floor to auto-comp every miss.",
            tags=["service-rescue", "pass"],
        ),
        LearningItem(
            id="l9",
            topic="line-opening",
            primary="Mise depth for the first hour should cover peak without restock panic — count back from covers, not from hope.",
            detail="For each station: portions prepped = covers × take-rate × 1.15 buffer. Sauces hot and strained. Garnish refreshed, not overnight wilt. If you restock from deep fridge mid-rush, your open count was wrong — note it for tomorrow.",
            tags=["line-opening", "mise"],
        ),
        LearningItem(
            id="l10",
            topic="service-rescue",
            primary="Allergy near-miss write-up same shift: what failed, who caught it, what changes on the matrix tomorrow.",
            detail="One page, no blame theatre. Matrix update, label change, or brief at next open. Near-misses that aren't written disappear into folklore — and folklore doesn't protect guests.",
            tags=["service-rescue", "allergen-matrix"],
        ),
    ]

    learning = LearningSection(
        pool=learning_pool,
        window_size=5,
        ring=1,
        topics_label="allergen-matrix + service-rescue + line-opening",
        advance_ms=20_000,
    )

    pins = [
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
    ]

    ring = [
        BriefingItem(
            id="r1",
            title="Show HN: offline-first kitchen ticket rail written in ~400 lines of C",
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
            title="Ask HN: how do you structure a personal ops board without it becoming a second job?",
            url="https://news.ycombinator.com",
            source="hn",
            points=156,
            comments=112,
        ),
        BriefingItem(
            id="r4",
            title="Someone posted their cassette deck maintenance checklist — oddly satisfying",
            url="https://x.com/explore",
            source="x",
        ),
        BriefingItem(
            id="r5",
            title="HN: Practical guide to reading apt and systemd status without the noise",
            url="https://news.ycombinator.com",
            source="hn",
            points=98,
            comments=41,
        ),
        BriefingItem(
            id="r6",
            title="Field notes from a week cooking only one protein — constraints breed clarity",
            url="https://x.com/explore",
            source="x",
        ),
        BriefingItem(
            id="r7",
            title="Show HN: tiny TUI for disk + failed units on a headless debian box",
            url="https://news.ycombinator.com",
            source="hn",
            points=67,
            comments=22,
        ),
        BriefingItem(
            id="r8",
            title="A calm take on why most personal dashboards die in month two",
            url="https://x.com/explore",
            source="x",
        ),
    ]

    briefing = BriefingSection(
        pins=pins,
        ring=ring,
        ring_index=0,
        ring_n=1,
        sources_label="x + hn",
        advance_ms=5_000,
    )

    machine = MachineSection(
        host="debian-minimal",
        disk_pct=42.0,
        free_gib=118.4,
        failed_units=0,
        net="wired",
        apt_updates=3,
    ).with_health()

    warnings = sum(1 for i in today.items if i.level == Level.warn)
    if machine.warn:
        warnings += 1

    status = (
        BoardStatus(label=f"worth a look — {warnings} warnings", warnings=warnings)
        if warnings
        else BoardStatus(label="ok · quiet", warnings=0)
    )

    return Board(
        header=BoardHeader(host="debian-minimal", updated_at=now, status=status),
        today=today,
        media=media,
        learning=learning,
        briefing=briefing,
        machine=machine,
    )
