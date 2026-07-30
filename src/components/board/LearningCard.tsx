import { useEffect, useMemo, useState } from "react";
import type { Board, LearningSection } from "@/lib/board-types";
import { TagChip } from "./TagChip";

export function LearningCard({
  board,
}: {
  board: Board;
  onBoard?: (b: Board) => void;
}) {
  const learning: LearningSection = board.learning;
  const pool = learning.pool;
  const windowSize = learning.window_size;
  const [offset, setOffset] = useState(0);
  const [ring, setRing] = useState(learning.ring);
  const [hovered, setHovered] = useState(false);
  const n = pool.length || 1;

  useEffect(() => {
    if (hovered || pool.length <= windowSize) return;
    const id = window.setInterval(() => {
      setOffset((o) => {
        const next = (o + 1) % n;
        if (next === 0) setRing((r) => r + 1);
        return next;
      });
    }, learning.advance_ms);
    return () => window.clearInterval(id);
  }, [hovered, pool.length, windowSize, learning.advance_ms, n]);

  const windowItems = useMemo(() => {
    if (!pool.length) return [];
    const out = [];
    for (let i = 0; i < Math.min(windowSize, pool.length); i++) {
      out.push(pool[(offset + i) % pool.length]!);
    }
    return out;
  }, [pool, offset, windowSize]);

  const i = pool.length ? offset + 1 : 0;
  const j = pool.length ? offset + windowItems.length : 0;

  return (
    <section
      className="board-card learning-card"
      data-accent="green"
      aria-label="learning"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <h2 className="board-card-title" data-accent="green">
        learning
      </h2>
      <div>
        {windowItems.map((item) => (
          <div key={`${item.id}-${offset}`} className="item-row">
            <div className="learning-primary">{item.primary}</div>
            <p className="mt-1 mb-0 text-sm text-muted text-pretty">{item.detail}</p>
            {item.tags?.length ? (
              <div className="mt-1 flex flex-wrap gap-1">
                {item.tags.map((t) => (
                  <TagChip key={t} tag={t} />
                ))}
              </div>
            ) : null}
          </div>
        ))}
        {!windowItems.length ? <p className="meta-dim">no learning items</p> : null}
      </div>
      <div className="board-card-footer">
        ring {ring} · {learning.topics_label} · {i}–{j} of {pool.length} ↻
        {hovered ? " · paused" : ""}
      </div>
    </section>
  );
}
