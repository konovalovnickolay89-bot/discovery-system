import { validateApiConfig } from "@/lib/api-config";

export type ApiFailureKind =
  | "misconfigured"
  | "unreachable"
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
        : "Showing last known board";

  const body =
    kind === "misconfigured"
      ? config.ok
        ? detail
        : config.reason
      : kind === "unreachable"
        ? detail ||
          "The FastAPI backend is not reachable. On discovery-system.grok.me " +
            "set VITE_API_BASE_URL to your API https origin (no browser tokens)."
        : detail || "Live sync is down; values may be stale.";

  return (
    <div className="api-failure-banner" role="alert" data-kind={kind} aria-live="polite">
      <div className="api-failure-title">{title}</div>
      <p className="api-failure-body">{body}</p>
      <ul className="api-failure-hints">
        <li>
          Web: <code>https://discovery-system.grok.me</code>
        </li>
        <li>
          API via <code>VITE_API_BASE_URL</code> · never put owner/bridge tokens in the browser
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
