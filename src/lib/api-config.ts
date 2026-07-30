/**
 * API origin for the authoritative backend.
 *
 * SECURITY: Never put CASUAL_BOARD_TOKEN (or any owner/bridge secret) in VITE_*
 * env vars or browser code. The web client is public (CORS-locked in production).
 * Approvals and bridge auth run from Debian/CLI only.
 *
 * DEVELOPMENT: VITE_API_BASE_URL empty → same-origin Vite proxy.
 * PRODUCTION (discovery-system.grok.me): VITE_API_BASE_URL = https://api…
 */

export const GROK_ME_WEB_ORIGIN = "https://discovery-system.grok.me";

export type ApiConfigStatus =
  | { ok: true; base: string; mode: "same-origin" | "external" }
  | { ok: false; reason: string; mode: "misconfigured" };

export function rawApiBase(): string {
  return (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ?? "";
}

export function isBrowserProductionHost(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname;
  return host === "discovery-system.grok.me" || host.endsWith(".grok.me");
}

export function validateApiConfig(): ApiConfigStatus {
  const raw = rawApiBase();
  const onGrokMe =
    isBrowserProductionHost() || (import.meta.env.PROD && !import.meta.env.DEV);

  if (!raw) {
    if (onGrokMe && typeof window !== "undefined") {
      return {
        ok: false,
        mode: "misconfigured",
        reason:
          "VITE_API_BASE_URL is not set. discovery-system.grok.me only hosts the web UI — " +
          "set VITE_API_BASE_URL to your FastAPI https origin and rebuild. " +
          "Do not put API tokens in the browser.",
      };
    }
    return { ok: true, base: "", mode: "same-origin" };
  }

  if (raw.startsWith("http://") && onGrokMe) {
    return {
      ok: false,
      mode: "misconfigured",
      reason:
        "VITE_API_BASE_URL must use https:// when the UI is on grok.me (mixed content).",
    };
  }

  if ((raw.includes("localhost") || raw.includes("127.0.0.1")) && onGrokMe) {
    return {
      ok: false,
      mode: "misconfigured",
      reason:
        "VITE_API_BASE_URL points at localhost — use a public https API origin.",
    };
  }

  try {
    // eslint-disable-next-line no-new
    new URL(raw);
  } catch {
    return {
      ok: false,
      mode: "misconfigured",
      reason: `VITE_API_BASE_URL is not a valid URL: ${raw}`,
    };
  }

  return { ok: true, base: raw.replace(/\/$/, ""), mode: "external" };
}

export function apiBase(): string {
  const v = validateApiConfig();
  if (!v.ok) return "";
  return v.base;
}

export function apiUrl(path: string): string {
  const base = apiBase();
  const p = path.startsWith("/") ? path : `/${path}`;
  if (!base) return p;
  return `${base}${p}`;
}

export function wsUrl(path: string): string {
  const base = apiBase();
  let httpOrigin: string;
  if (base) {
    httpOrigin = base;
  } else if (typeof window !== "undefined") {
    httpOrigin = window.location.origin;
  } else {
    httpOrigin = "http://127.0.0.1:8080";
  }
  const u = new URL(path, httpOrigin.endsWith("/") ? httpOrigin : `${httpOrigin}/`);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  return u.toString();
}

/** Public JSON headers only — no Authorization. */
export function publicHeaders(): HeadersInit {
  return {
    "content-type": "application/json",
    accept: "application/json",
  };
}
