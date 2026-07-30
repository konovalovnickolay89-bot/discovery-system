import { apiUrl, wsUrl } from "./api-config";
import {
  clearSession,
  loadSession,
  saveSession,
  sessionAccessToken,
  sessionAuthHeaders,
} from "./session";
import type {
  Board,
  CaptureResponse,
  ChatResponse,
  CommandResponse,
  HealthResponse,
} from "./board-types";
import { FALLBACK_BOARD } from "./board-fallback";

export class AuthError extends Error {
  constructor(message = "session expired") {
    super(message);
    this.name = "AuthError";
  }
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { ...sessionAuthHeaders(), ...(init?.headers ?? {}) },
  });
  if (res.status === 401) {
    clearSession();
    throw new AuthError("session expired or signed out");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function login(password: string): Promise<void> {
  const res = await fetch(apiUrl("/v1/auth/login"), {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || "login failed");
  }
  const data = (await res.json()) as {
    access_token: string;
    expires_at: number;
    scope: string;
  };
  saveSession({
    access_token: data.access_token,
    expires_at: data.expires_at,
    scope: data.scope,
  });
}

export function logout(): void {
  clearSession();
}

export function isSignedIn(): boolean {
  return !!loadSession();
}

export async function fetchHealth(): Promise<HealthResponse | null> {
  try {
    const res = await fetch(apiUrl("/health"), { headers: { accept: "application/json" } });
    if (!res.ok) return null;
    return (await res.json()) as HealthResponse;
  } catch {
    return null;
  }
}

export async function fetchBoard(): Promise<Board> {
  return getJson<Board>(apiUrl("/v1/board"));
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
    body: JSON.stringify({ command, payload, source: "web", actor: "phone" }),
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
  onAuthError?: () => void;
}): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let retry = 0;
  let timer: number | undefined;

  const connect = () => {
    if (closed) return;
    const token = sessionAccessToken();
    if (!token && isSignedIn() === false) {
      opts.onAuthError?.();
      return;
    }
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
        const msg = JSON.parse(String(ev.data)) as { type?: string; board?: Board };
        if (msg.board && (msg.type === "snapshot" || msg.type === "revision")) {
          opts.onBoard(msg.board);
        }
      } catch {
        /* ignore */
      }
    };
    ws.onclose = (ev) => {
      if (ev.code === 4401) {
        clearSession();
        opts.onAuthError?.();
        return;
      }
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
