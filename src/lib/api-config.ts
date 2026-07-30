/**
 * API origin for the authoritative backend.
 *
 * DEVELOPMENT (Grok Build sandbox / local Vite):
 *   VITE_API_BASE_URL = unset / empty
 *   → same-origin paths; Vite proxies /v1 and /health to backend :8090
 *
 * PRODUCTION (https://discovery-system.grok.me):
 *   VITE_API_BASE_URL = absolute https origin of the Python API
 *   e.g. https://casual-board-api.your-domain.tld
 *        https://xxxx.trycloudflare.com  (temporary tunnel)
 *   MUST be set at build time — grok.me does not host FastAPI.
 *
 * Never point production UI at http:// or localhost.
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

/** Validate client-side API config for the current runtime. */
export function validateApiConfig(): ApiConfigStatus {
  const raw = rawApiBase();
  const onGrokMe =
    isBrowserProductionHost() ||
    (import.meta.env.PROD && !import.meta.env.DEV);

  if (!raw) {
    if (onGrokMe && typeof window !== "undefined") {
      return {
        ok: false,
        mode: "misconfigured",
        reason:
          "VITE_API_BASE_URL is not set. discovery-system.grok.me only hosts the web UI — " +
          "set VITE_API_BASE_URL to your FastAPI https origin and rebuild.",
      };
    }
    return { ok: true, base: "", mode: "same-origin" };
  }

  if (raw.startsWith("http://") && onGrokMe) {
    return {
      ok: false,
      mode: "misconfigured",
      reason:
        "VITE_API_BASE_URL must use https:// when the UI is on grok.me (browsers block mixed content).",
    };
  }

  if (raw.includes("localhost") || raw.includes("127.0.0.1")) {
    if (onGrokMe) {
      return {
        ok: false,
        mode: "misconfigured",
        reason:
          "VITE_API_BASE_URL points at localhost — phone browsers cannot reach your build machine. " +
          "Use a public https API origin (Cloudflare Tunnel or your domain).",
      };
    }
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
  // If misconfigured on grok.me, still attempt same-origin so failure is visible
  if (!base) {
    const v = validateApiConfig();
    if (!v.ok) return p; // will 404 on grok.me → clear failure
    return p;
  }
  return `${base}${p}`;
}

export function wsUrl(path: string, token?: string): string {
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
  // HTTPS page → WSS; HTTP page → WS
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  if (token) u.searchParams.set("token", token);
  return u.toString();
}

export function authHeaders(): HeadersInit {
  const token = (import.meta.env.VITE_API_TOKEN as string | undefined)?.trim();
  const h: Record<string, string> = {
    "content-type": "application/json",
    accept: "application/json",
  };
  if (token) h.authorization = `Bearer ${token}`;
  return h;
}
