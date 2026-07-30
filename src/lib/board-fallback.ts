import type { Board } from "./board-types";

/** Offline / first-paint fallback until API connects. */
export const FALLBACK_BOARD: Board = {
  meta: {
    revision: 0,
    generated_at: "2026-07-29T12:00:00.000Z",
    updated_at: "2026-07-29T12:00:00.000Z",
    host_label: "casual-board",
    status: { label: "connecting…", warnings: 0 },
  },
  today: {
    items: [],
    empty_footer: "waiting for board snapshot…",
  },
  media: {
    state: "idle",
    current: null,
    queue: [],
    cassette: true,
    volume: 55,
    playlist_label: "CHILLOUT MUSIC 2026",
    playlist_url: "https://www.youtube.com/playlist?list=PLchillout2026",
    speaker: "speaker up",
    player: "mpv",
    fetcher: "ytdl",
    cassette_engine: "ffmpeg cassette",
    cassette_profile: "chrome-type-ii",
    cassette_repo: "AARomanov1985/Audio-Cassette-Simulation",
    path_label: "ytdl → mpv → ffmpeg cassette → out",
  },
  learning: {
    pool: [],
    window_size: 5,
    ring: 1,
    topics_label: "—",
    advance_ms: 20_000,
  },
  briefing: {
    pins: [],
    ring: [],
    ring_index: 0,
    ring_n: 1,
    sources_label: "x + hn",
    advance_ms: 5_000,
  },
  machine: {
    host: "—",
    disk_pct: 0,
    free_gib: 0,
    failed_units: 0,
    net: "wired",
    apt_updates: 0,
    warn: false,
  },
};
