/**
 * API origin for FastAPI.
 * SECURITY: Never put CASUAL_BOARD_TOKEN / BRIDGE_TOKEN / UI password long-term
 * secrets in VITE_*. Session tokens live only in sessionStorage after login.
 */

export const GROK_ME_WEB_ORIGIN = "https://discovery-system.grok.me";
export const DEFAULT_PROD_API = "https://api.apidiscoverysolution.uk";

export type ApiConfigStatus =
  | { ok: true; base: string; mode: "same-origin" | "external" }
  | { ok: false; reason: string; mode: "misconfigured" };

export function rawApiBase(): string {
  return (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ?? "";
}

export function isBrowserProductionHost(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.location.hostname === "discovery-system.grok.me" ||
    window.location.hostname.endsWith(".grok.me")
  );
}

export function validateApiConfig(): ApiConfigStatus {
  const raw = rawApiBase();
  const onGrokMe = isBrowserProductionHost() || (import.meta.env.PROD && !import.meta.env.DEV);

  if (!raw) {
    if (onGrokMe && typeof window !== "undefined") {
      return {
        ok: false,
        mode: "misconfigured",
        reason:
          "VITE_API_BASE_URL is not set. Production UI must use " +
          `${DEFAULT_PROD_API} (rebuild). No API secrets in the browser.`,
      };
    }
    return { ok: true, base: "", mode: "same-origin" };
  }
  if (raw.startsWith("http://") && onGrokMe) {
    return {
      ok: false,
      mode: "misconfigured",
      reason: "VITE_API_BASE_URL must be https:// on grok.me",
    };
  }
  try {
    // eslint-disable-next-line no-new
    new URL(raw);
  } catch {
    return { ok: false, mode: "misconfigured", reason: `Invalid VITE_API_BASE_URL: ${raw}` };
  }
  return { ok: true, base: raw.replace(/\/$/, ""), mode: "external" };
}

export function apiBase(): string {
  const v = validateApiConfig();
  return v.ok ? v.base : "";
}

export function apiUrl(path: string): string {
  const base = apiBase();
  const p = path.startsWith("/") ? path : `/${path}`;
  return base ? `${base}${p}` : p;
}

export function wsUrl(path: string, accessToken?: string | null): string {
  const base = apiBase();
  let httpOrigin: string;
  if (base) httpOrigin = base;
  else if (typeof window !== "undefined") httpOrigin = window.location.origin;
  else httpOrigin = "http://127.0.0.1:8080";
  const u = new URL(path, httpOrigin.endsWith("/") ? httpOrigin : `${httpOrigin}/`);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  if (accessToken) u.searchParams.set("access_token", accessToken);
  return u.toString();
}
