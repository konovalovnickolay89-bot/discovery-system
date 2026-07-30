import { apiUrl, authHeaders, wsUrl } from "./api-config";
import type {
  Board,
  CaptureResponse,
  ChatResponse,
  CommandResponse,
  HealthResponse,
} from "./board-types";
import { FALLBACK_BOARD } from "./board-fallback";

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { ...authHeaders(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchHealth(): Promise<HealthResponse | null> {
  try {
    return await getJson<HealthResponse>(apiUrl("/health"));
  } catch {
    return null;
  }
}

export async function fetchBoard(): Promise<Board> {
  try {
    return await getJson<Board>(apiUrl("/v1/board"));
  } catch {
    return FALLBACK_BOARD;
  }
}

export async function postCapture(note: string): Promise<CaptureResponse> {
  return getJson<CaptureResponse>(apiUrl("/v1/captures"), {
    method: "POST",
    body: JSON.stringify({ note, source: "web", use_ai: true }),
  });
}

export async function postCommand(
  command: string,
  payload: Record<string, unknown> = {},
): Promise<CommandResponse> {
  return getJson<CommandResponse>(apiUrl("/v1/commands"), {
    method: "POST",
    body: JSON.stringify({
      command,
      payload,
      source: "web",
      actor: "phone",
    }),
  });
}

export async function postChat(message: string): Promise<ChatResponse> {
  return getJson<ChatResponse>(apiUrl("/v1/chat"), {
    method: "POST",
    body: JSON.stringify({ message, channel: "hermes", source: "web" }),
  });
}

export function connectBoardSocket(opts: {
  onBoard: (b: Board) => void;
  onStatus?: (s: string) => void;
}): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let retry = 0;
  let timer: number | undefined;
  const token = (import.meta.env.VITE_API_TOKEN as string | undefined)?.trim();

  const connect = () => {
    if (closed) return;
    try {
      ws = new WebSocket(wsUrl("/v1/board/ws", token));
    } catch {
      opts.onStatus?.("offline");
      schedule();
      return;
    }
    ws.onopen = () => {
      retry = 0;
      opts.onStatus?.("live");
      ws?.send("ping");
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data)) as {
          type?: string;
          board?: Board;
        };
        if (msg.board && (msg.type === "snapshot" || msg.type === "revision")) {
          opts.onBoard(msg.board);
        }
      } catch {
        /* ignore */
      }
    };
    ws.onclose = () => {
      opts.onStatus?.("reconnecting…");
      schedule();
    };
    ws.onerror = () => ws?.close();
  };

  const schedule = () => {
    if (closed) return;
    const delay = Math.min(10000, 400 * 2 ** retry);
    retry += 1;
    timer = window.setTimeout(connect, delay);
  };

  connect();
  return () => {
    closed = true;
    if (timer) window.clearTimeout(timer);
    ws?.close();
  };
}
