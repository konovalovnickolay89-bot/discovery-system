import type { CookConsultation } from "@/lib/cook-api";

function rel(iso?: string | null) {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 8) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function mark(ok: boolean) {
  return ok ? "✓" : "·";
}

export function CookActiveTasks({
  tasks,
  onOpen,
}: {
  tasks: Array<Partial<CookConsultation> & { id: string; title?: string; mode?: string }>;
  onOpen: (id: string) => void;
}) {
  if (!tasks.length) {
    return (
      <section className="board-card" data-accent="green" aria-label="Cook Studio tasks">
        <h2 className="board-card-title" data-accent="green">
          cook studio · tasks
        </h2>
        <p className="meta-dim m-0 text-sm">No active Cook Studio tasks.</p>
      </section>
    );
  }

  return (
    <section className="board-card" data-accent="green" aria-label="Cook Studio tasks">
      <h2 className="board-card-title" data-accent="green">
        cook studio · active
      </h2>
      <div className="flex flex-col gap-2">
        {tasks.map((t) => {
          const ts = t.task_status || "";
          const gr = t.graph_recall_status || "not_requested";
          const safetyOk = ["safety_checked", "local_plan_ready", "kitchen_memory_queued", "kitchen_memory_working", "kitchen_memory_returned", "needs_review", "saved_as_dish_or_component"].includes(ts) || !!t.local_safety_plan;
          const localReady = [
            "local_plan_ready",
            "kitchen_memory_queued",
            "kitchen_memory_working",
            "kitchen_memory_returned",
            "needs_review",
            "saved_as_dish_or_component",
            "blocked",
          ].includes(ts);
          const next =
            ts === "blocked"
              ? "Disposal / escalate"
              : gr === "queued"
                ? "Kitchen memory queued"
                : gr === "leased"
                  ? "Kitchen memory working"
                  : gr === "failed"
                    ? "Local plan only"
                    : gr === "completed"
                      ? "Review kitchen memory"
                      : "Review local plan";
          return (
            <button
              key={t.id}
              type="button"
              className="ec-route w-full text-left"
              onClick={() => onOpen(t.id)}
            >
              <div className="font-mono text-xs uppercase tracking-wide text-fg">
                {(t.mode || "cook").toUpperCase()} · {t.title || t.id}
              </div>
              <div className="meta-dim mt-1 space-y-0.5 text-sm">
                <div>
                  Safety checked {mark(safetyOk || ts !== "draft")}
                </div>
                <div>Local plan ready {mark(localReady)}</div>
                <div>
                  Kitchen memory{" "}
                  {gr === "not_requested"
                    ? "local only"
                    : gr === "queued"
                      ? "queued"
                      : gr === "leased"
                        ? "working"
                        : gr === "completed"
                          ? "returned"
                          : gr === "failed"
                            ? "failed"
                            : gr}
                </div>
                <div>Next: {next}</div>
                <div>Updated: {rel(t.updated_at)}</div>
                {t.blocked_reason ? (
                  <div className="level-warn">{t.blocked_reason}</div>
                ) : null}
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
