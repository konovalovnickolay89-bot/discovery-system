/** Board + API types aligned with backend/app/models.py */

export type Level = "info" | "warn" | "highlight" | "dim";
export type Freshness = "fresh" | "stale" | "unknown";

export type RecipeSpine = {
  one: string;
  why: string;
  how: string;
  roles: string;
  mise_1: string;
  cost_portion: string;
  watch: string;
  allergens: string;
  parents: string;
  service_pass: string;
};

export type TodayItem = {
  id: string;
  text: string;
  level: Level;
  tags: string[];
  url?: string | null;
  detail?: string | null;
  kind: "routine" | "reminder" | "capture" | "recipe";
  source?: string;
  recipe?: RecipeSpine | null;
};

export type TodaySection = {
  items: TodayItem[];
  empty_footer: string;
  freshness?: Freshness;
};

export type PlayState = "idle" | "playing" | "paused";

export type Track = {
  id: string;
  title: string;
  artist: string;
  yt_id?: string | null;
  duration_s?: number | null;
};

export type MediaSection = {
  state: PlayState;
  current: Track | null;
  queue: Track[];
  cassette: boolean;
  volume: number;
  playlist_label: string;
  playlist_url: string;
  speaker: string;
  player: string;
  fetcher: string;
  cassette_engine: string;
  cassette_profile: string;
  cassette_repo: string;
  path_label: string;
  freshness?: Freshness;
  note?: string | null;
};

export type LearningItem = {
  id: string;
  topic: string;
  primary: string;
  detail: string;
  tags: string[];
};

export type LearningSection = {
  pool: LearningItem[];
  window_size: number;
  ring: number;
  topics_label: string;
  advance_ms: number;
};

export type BriefingItem = {
  id: string;
  title: string;
  url: string;
  source?: "hn" | "x";
  points?: number | null;
  comments?: number | null;
  level?: Level;
};

export type BriefingSection = {
  pins: BriefingItem[];
  ring: BriefingItem[];
  ring_index: number;
  ring_n: number;
  sources_label: string;
  advance_ms: number;
};

export type MachineSection = {
  host: string;
  disk_pct: number;
  free_gib: number;
  failed_units: number;
  net: "wired" | "wifi" | "down";
  apt_updates: number;
  warn: boolean;
  detail?: string | null;
  freshness?: Freshness;
};

export type BoardStatus = {
  label: string;
  warnings: number;
  freshness?: Freshness;
};

export type BoardMeta = {
  revision: number;
  generated_at: string;
  updated_at: string;
  host_label: string;
  status: BoardStatus;
};

export type Board = {
  meta: BoardMeta;
  today: TodaySection;
  media: MediaSection;
  learning: LearningSection;
  briefing: BriefingSection;
  machine: MachineSection;
};

export type HealthResponse = {
  ok: boolean;
  version?: string;
  env?: string;
  revision?: number;
  auth_mode?: string;
  pydantic?: string;
  pydantic_ai_available?: boolean;
  ai_provider?: string;
  data_dir?: string;
  time?: string;
};

export type CaptureResponse = {
  draft: {
    title: string;
    body: string;
    tags: string[];
    level: Level;
    suggested_when: string;
  };
  item: TodayItem;
  board: Board;
  used_ai: boolean;
  ai_provider?: string;
};

export type CommandResponse = {
  action: {
    id: string;
    command: string;
    status: string;
    message: string;
    job_id?: string | null;
  };
  board: Board | null;
  job?: {
    id: string;
    status: string;
    command: string;
  } | null;
};

export type ChatResponse = {
  ok: boolean;
  reply: string;
  suggested_commands: string[];
  board: Board | null;
};
