import { useEffect, useState } from "react";
import type { BoardMeta, HealthResponse } from "@/lib/board-types";

function formatLocalTime(d: Date) {
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function relativeUpdated(iso: string, now: number) {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "updated —";
  const sec = Math.max(0, Math.floor((now - t) / 1000));
  if (sec < 5) return "synced just now";
  if (sec < 60) return `synced ${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `synced ${min}m ago`;
  return `synced ${Math.floor(min / 60)}h ago`;
}

export function HeaderBar({
  meta,
  health,
  connection,
}: {
  meta: BoardMeta;
  health: HealthResponse | null;
  connection: string;
}) {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const warn = meta.status.warnings > 0;

  return (
    <header className="header-bar">
      <span className="tabular text-fg">
        {now == null ? "--:--:--" : formatLocalTime(new Date(now))}
      </span>
      <span className="sep">·</span>
      <span>{meta.host_label}</span>
      <span className="sep">·</span>
      <span className="tabular">rev {meta.revision}</span>
      <span className="sep">·</span>
      <span>{now == null ? "synced …" : relativeUpdated(meta.updated_at, now)}</span>
      <span className="sep">·</span>
      <span className={warn ? "status-warn" : "status-ok"}>{meta.status.label}</span>
      <span className="sep">·</span>
      <span>{connection}</span>
      {health?.ok ? (
        <>
          <span className="sep">·</span>
          <span>api ok</span>
        </>
      ) : null}
    </header>
  );
}
