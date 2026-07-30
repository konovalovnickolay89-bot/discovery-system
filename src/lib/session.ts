/** Browser session storage — short-lived API session only (never owner/bridge tokens). */

const KEY = "casual_board_session_v1";

export type StoredSession = {
  access_token: string;
  expires_at: number;
  scope: string;
};

export function loadSession(): StoredSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as StoredSession;
    if (!s.access_token || !s.expires_at) return null;
    if (s.expires_at * 1000 < Date.now() + 5_000) {
      clearSession();
      return null;
    }
    return s;
  } catch {
    return null;
  }
}

export function saveSession(s: StoredSession): void {
  sessionStorage.setItem(KEY, JSON.stringify(s));
}

export function clearSession(): void {
  sessionStorage.removeItem(KEY);
}

export function sessionAuthHeaders(): HeadersInit {
  const s = loadSession();
  const h: Record<string, string> = {
    "content-type": "application/json",
    accept: "application/json",
  };
  if (s?.access_token) h.authorization = `Bearer ${s.access_token}`;
  return h;
}

export function sessionAccessToken(): string | null {
  return loadSession()?.access_token ?? null;
}
