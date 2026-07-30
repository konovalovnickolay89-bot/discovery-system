import { useEffect, useMemo, useState } from "react";
import type { BriefingSection } from "@/lib/board-types";
import { TagChip } from "./TagChip";

export function BriefingCard({ briefing }: { briefing: BriefingSection }) {
  const [offset, setOffset] = useState(0);
  const [ringN, setRingN] = useState(briefing.ring_n);
  const [hovered, setHovered] = useState(false);
  const pool = briefing.ring;
  const n = pool.length || 1;
  const windowSize = 5;

  useEffect(() => {
    if (hovered || pool.length <= windowSize) return;
    const id = window.setInterval(() => {
      setOffset((o) => {
        const next = (o + 1) % n;
        if (next === 0) setRingN((r) => r + 1);
        return next;
      });
    }, briefing.advance_ms);
    return () => window.clearInterval(id);
  }, [hovered, pool.length, briefing.advance_ms, n]);

  const windowItems = useMemo(() => {
    if (!pool.length) return [];
    const out = [];
    for (let i = 0; i < Math.min(windowSize, pool.length); i++) {
      out.push(pool[(offset + i) % pool.length]!);
    }
    return out;
  }, [pool, offset]);

  const i = pool.length ? offset + 1 : 0;
  const j = pool.length ? offset + windowItems.length : 0;

  return (
    <section
      className="board-card"
      data-accent="purple"
      aria-label="briefing"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <h2 className="board-card-title" data-accent="purple">
        briefing
      </h2>
      <div className="pin-block">
        {briefing.pins.map((pin) => (
          <div key={pin.id} className="item-row">
            <div className={`level-${pin.level || "info"}`}>{pin.title}</div>
            <div className="mt-1 flex flex-wrap gap-1">
              <TagChip tag={pin.source || "x"} />
            </div>
            <a className="item-url" href={pin.url} target="_blank" rel="noreferrer">
              {pin.url}
            </a>
          </div>
        ))}
      </div>
      <div className="ring-divider" />
      <div>
        {windowItems.map((item) => (
          <div key={`${item.id}-${offset}`} className="item-row">
            <div className={`level-${item.level || "info"}`}>{item.title}</div>
            <div className="mt-1 flex flex-wrap items-center gap-1">
              <TagChip tag={item.source || "hn"} />
              {item.points != null || item.comments != null ? (
                <span className="meta-dim font-mono text-xs">
                  · {item.points != null ? `${item.points} pts` : ""}
                  {item.points != null && item.comments != null ? " · " : ""}
                  {item.comments != null ? `${item.comments} c` : ""}
                </span>
              ) : null}
            </div>
            <a className="item-url" href={item.url} target="_blank" rel="noreferrer">
              {item.url}
            </a>
          </div>
        ))}
      </div>
      <div className="board-card-footer">
        ring {ringN} · {briefing.sources_label} · {i}–{j} of {pool.length} ↻
        {hovered ? " · paused" : ""}
      </div>
    </section>
  );
}
