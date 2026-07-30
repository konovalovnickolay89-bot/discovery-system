import { useState } from "react";
import type { Board, TodayItem } from "@/lib/board-types";
import { postCapture } from "@/lib/board-api";
import { TagChip } from "./TagChip";

const RECIPE_LABELS: { key: keyof NonNullable<TodayItem["recipe"]>; label: string }[] = [
  { key: "one", label: "ONE" },
  { key: "why", label: "WHY" },
  { key: "how", label: "HOW" },
  { key: "roles", label: "ROLES" },
  { key: "mise_1", label: "MISE 1" },
  { key: "cost_portion", label: "COST/PORTION" },
  { key: "watch", label: "WATCH" },
  { key: "allergens", label: "ALLERGENS" },
  { key: "parents", label: "PARENTS" },
  { key: "service_pass", label: "SERVICE/PASS" },
];

function ItemBlock({ item }: { item: TodayItem }) {
  return (
    <div className="item-row">
      <div className={`level-${item.level}`}>{item.text}</div>
      {item.tags?.length ? (
        <div className="mt-1 flex flex-wrap gap-1">
          {item.tags.map((t) => (
            <TagChip key={t} tag={t} />
          ))}
        </div>
      ) : null}
      {item.url ? (
        <a className="item-url" href={item.url} target="_blank" rel="noreferrer">
          {item.url}
        </a>
      ) : null}
      {item.recipe ? (
        <dl className="recipe-spine">
          {RECIPE_LABELS.map(({ key, label }) => (
            <div key={key}>
              <dt>{label}</dt>
              <dd>{item.recipe![key]}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

export function TodayCard({
  board,
  onBoard,
}: {
  board: Board;
  onBoard: (b: Board) => void;
}) {
  const { today } = board;
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [meta, setMeta] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submitCapture() {
    if (!note.trim() || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await postCapture(note.trim());
      setMeta(res.used_ai ? "pydantic-ai · structured" : "deterministic · structured");
      onBoard(res.board);
      setNote("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "capture failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="board-card" data-accent="peach" aria-label="today">
      <h2 className="board-card-title" data-accent="peach">
        today
      </h2>

      {today.items.length === 0 ? (
        <p className="meta-dim">{today.empty_footer}</p>
      ) : (
        <div>
          {today.items.map((item) => (
            <ItemBlock key={item.id} item={item} />
          ))}
        </div>
      )}

      <div className="ai-panel">
        <label className="meta-dim text-xs font-mono tracking-wide uppercase">
          capture · hosted
        </label>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Note → structured capture (syncs to Debian CLI)"
          rows={2}
        />
        <div className="ai-actions">
          <button
            type="button"
            className="primary"
            disabled={busy || !note.trim()}
            onClick={() => void submitCapture()}
          >
            {busy ? "structuring…" : "structure capture"}
          </button>
          {meta ? <span className="ai-meta">{meta}</span> : null}
          {err ? <span className="ai-meta level-warn">{err}</span> : null}
        </div>
      </div>

      <div className="board-card-footer">
        {today.items.length === 0
          ? today.empty_footer
          : `${today.items.length} items · rev ${board.meta.revision}`}
      </div>
    </section>
  );
}
