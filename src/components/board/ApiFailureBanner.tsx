import { validateApiConfig } from "@/lib/api-config";

export type ApiFailureKind =
  | "misconfigured"
  | "unreachable"
  | "auth"
  | "offline-cache";

export function ApiFailureBanner({
  kind,
  detail,
  lastSync,
}: {
  kind: ApiFailureKind | null;
  detail?: string | null;
  lastSync?: string | null;
}) {
  if (!kind) return null;

  const config = validateApiConfig();
  const title =
    kind === "misconfigured"
      ? "API not configured for production"
      : kind === "unreachable"
        ? "Cannot reach board API"
        : kind === "auth"
          ? "API authentication failed"
          : "Showing last known board";

  const body =
    kind === "misconfigured"
      ? config.ok
        ? detail
        : config.reason
      : kind === "unreachable"
        ? detail ||
          "The FastAPI backend is not reachable from this page. " +
            "On discovery-system.grok.me the API must be a separate https host " +
            "(VITE_API_BASE_URL). Debian/CLI can still work offline from cache."
        : kind === "auth"
          ? detail || "Check VITE_API_TOKEN / CASUAL_BOARD_TOKEN."
          : detail || "Live sync is down; values may be stale.";

  return (
    <div
      className="api-failure-banner"
      role="alert"
      data-kind={kind}
      aria-live="polite"
    >
      <div className="api-failure-title">{title}</div>
      <p className="api-failure-body">{body}</p>
      <ul className="api-failure-hints">
        <li>
          Web origin: <code>https://discovery-system.grok.me</code>
        </li>
        <li>
          API must be external · set <code>VITE_API_BASE_URL</code> at build time
        </li>
        {lastSync ? (
          <li>
            Last sync: <code>{lastSync}</code>
          </li>
        ) : null}
      </ul>
    </div>
  );
}
