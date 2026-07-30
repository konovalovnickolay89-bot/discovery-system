import { useCallback, useEffect, useMemo, useState } from "react";
import type { Board } from "@/lib/board-types";
import { AuthError, postCapture } from "@/lib/board-api";
import {
  createConsultation,
  getConsultation,
  listConsultations,
  listIngredients,
  listProduce,
  type CookConsultation,
  type Ingredient,
  type ProduceLot,
} from "@/lib/cook-api";
import { CookStudioWorkspace } from "./CookStudioCard";

const MODES = [
  { id: "build", label: "Build" },
  { id: "rescue", label: "Rescue" },
  { id: "service", label: "Service" },
  { id: "develop", label: "Develop" },
] as const;

const TRACE = [
  { value: "labelled_chilled_known", label: "Labelled, chilled & known" },
  { value: "clean_raw_trim", label: "Clean raw trim" },
  { value: "unknown", label: "Unknown" },
  { value: "guest_exposed_buffet", label: "Guest-exposed buffet" },
] as const;

const CTX = [
  { value: "staff_meal", label: "Staff meal" },
  { value: "canteen", label: "Canteen" },
  { value: "breakfast", label: "Breakfast" },
  { value: "banqueting", label: "Banqueting" },
  { value: "a_la_carte", label: "À la carte" },
  { value: "home", label: "Home" },
  { value: "undecided", label: "Undecided" },
] as const;

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

function mark(done: boolean) {
  return done ? "✓" : "·";
}

function planOf(c: CookConsultation | null) {
  return c?.local_safety_plan as CookConsultation["local_safety_plan"] | undefined;
}

function pipeline(c: CookConsultation | null) {
  if (!c) {
    return {
      safety: false,
      local: false,
      km: "none" as const,
      next: "Pick a mode and run a quick plan",
    };
  }
  const ts = c.task_status;
  const gr = c.graph_recall_status;
  const safety =
    ts !== "draft" ||
    !!c.local_safety_plan ||
    [
      "blocked",
      "local_plan_ready",
      "kitchen_memory_queued",
      "kitchen_memory_working",
      "kitchen_memory_returned",
    ].includes(ts);
  const local = [
    "local_plan_ready",
    "kitchen_memory_queued",
    "kitchen_memory_working",
    "kitchen_memory_returned",
    "needs_review",
    "saved_as_dish_or_component",
    "blocked",
  ].includes(ts);
  let km: "none" | "queued" | "working" | "returned" | "unavailable" = "none";
  if (gr === "queued") km = "queued";
  else if (gr === "leased") km = "working";
  else if (gr === "completed") km = "returned";
  else if (gr === "failed") km = "unavailable";

  let next = "Review local plan";
  if (ts === "blocked") next = "Disposal / escalate — no cook-forward routes";
  else if (km === "queued") next = "Kitchen memory pending";
  else if (km === "working") next = "Kitchen memory working";
  else if (km === "unavailable") next = "Local plan only — Kitchen memory unavailable";
  else if (km === "returned") next = "Review evidence & finish";
  else if (local) next = c.local_safety_plan?.recommended_action || "Execute primary plan";

  return { safety, local, km, next };
}

function kmLabel(km: ReturnType<typeof pipeline>["km"]) {
  if (km === "none") return "local plan only";
  if (km === "queued") return "pending";
  if (km === "working") return "working";
  if (km === "returned") return "returned";
  return "unavailable";
}

function verdictText(c: CookConsultation | null) {
  const d = c?.local_safety_plan?.decision;
  if (!d) return null;
  const v = (d.verdict || "").replace(/_/g, " ");
  return `${v}${d.title ? ` — ${d.title}` : ""}`;
}

function EvidenceStrip({ c }: { c: CookConsultation }) {
  const [open, setOpen] = useState(false);
  const plan = planOf(c);
  if (!plan) return null;
  const count = plan.evidence_source_count ?? 0;
  const tier = plan.evidence_best_tier;
  const gate = plan.evidence_gate_status || "";
  const research = plan.evidence_research_status || "not_needed";
  const verified = !!plan.evidence_verified;
  const cites = plan.evidence_citations || [];
  const unknowns = plan.evidence_unknowns || [];

  let statusLine = "";
  if (c.task_status === "blocked") statusLine = "Blocked by local safety";
  else if (c.graph_recall_status === "failed") statusLine = "Kitchen memory unavailable";
  else if (c.graph_recall_status === "queued" || c.graph_recall_status === "leased")
    statusLine = "Kitchen memory pending";
  else if (research === "pending_review") statusLine = "Research pending review";
  else if (gate === "insufficient_evidence") statusLine = "Insufficient evidence";
  else if (verified) statusLine = "Cited sources on file";
  else if (c.graph_recall_status === "completed") statusLine = "Kitchen memory returned — not auto-verified";

  if (!statusLine && !count && c.graph_recall_status === "not_requested") return null;

  return (
    <div className="ec-route mt-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="font-mono text-xs uppercase tracking-wide text-muted">Evidence</div>
        <button type="button" className="signout-btn" onClick={() => setOpen((o) => !o)}>
          {open ? "hide citations" : "citations"}
        </button>
      </div>
      <div className="meta-dim mt-1 space-y-0.5 text-sm">
        <div>
          Sources: {count}
          {tier != null ? ` · best tier ${tier}` : ""}
          {verified ? " · verified" : " · not verified professional recommendation"}
        </div>
        {statusLine ? <div className={verified ? "status-ok" : "level-warn"}>{statusLine}</div> : null}
      </div>
      {open ? (
        <div className="mt-2 space-y-2 text-sm">
          {cites.length ? (
            <ul className="m-0 list-disc pl-4">
              {cites.map((ci) => (
                <li key={ci.source_id + (ci.path_or_url || "")}>
                  <strong>{ci.title}</strong>
                  {ci.authority_tier != null ? ` · T${ci.authority_tier}` : ""}
                  {ci.path_or_url ? (
                    <div className="meta-dim font-mono text-xs break-all">{ci.path_or_url}</div>
                  ) : null}
                  {ci.excerpt ? <div className="meta-dim">{ci.excerpt}</div> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="meta-dim m-0">No resolvable citations yet.</p>
          )}
          {unknowns.length ? (
            <div>
              <div className="ec-step">Unknowns / conflicts</div>
              <ul className="m-0 list-disc pl-4 text-sm">
                {unknowns.map((u) => (
                  <li key={u}>{u}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function EvolvingCookCard({
  onBoard,
  onAuthLost,
  liveTask,
  activeTasks = [],
}: {
  onBoard?: (b: Board) => void;
  onAuthLost?: () => void;
  liveTask?: Record<string, unknown> | null;
  activeTasks?: Array<Partial<CookConsultation> & { id: string }>;
}) {
  const [mode, setMode] = useState<(typeof MODES)[number]["id"]>("rescue");
  const [problem, setProblem] = useState("");
  const [trace, setTrace] = useState<(typeof TRACE)[number]["value"]>("labelled_chilled_known");
  const [ctx, setCtx] = useState<(typeof CTX)[number]["value"]>("staff_meal");
  const [allergens, setAllergens] = useState("");
  const [outcome, setOutcome] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<CookConsultation | null>(null);
  const [produce, setProduce] = useState<ProduceLot[]>([]);
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [selLots, setSelLots] = useState<string[]>([]);
  const [selIngs, setSelIngs] = useState<string[]>([]);
  const [fullOpen, setFullOpen] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const loadLib = useCallback(async () => {
    try {
      const [p, i] = await Promise.all([listProduce(), listIngredients()]);
      setProduce(p);
      setIngredients(i);
    } catch (e) {
      if (e instanceof AuthError) onAuthLost?.();
    }
  }, [onAuthLost]);

  useEffect(() => {
    void loadLib();
  }, [loadLib]);

  useEffect(() => {
    const id =
      (typeof liveTask?.id === "string" && liveTask.id) || activeTasks[0]?.id || null;
    if (!id) return;
    void getConsultation(id)
      .then(setActive)
      .catch(() => undefined);
  }, [liveTask, activeTasks]);

  useEffect(() => {
    if (active || !activeTasks.length) return;
    void listConsultations(true)
      .then((rows) => {
        if (rows[0]) setActive(rows[0]);
      })
      .catch(() => undefined);
  }, [activeTasks, active]);

  const pipe = useMemo(() => pipeline(active), [active]);
  const selectedProduce = produce.filter((p) => selLots.includes(p.id));
  const selectedIngs = ingredients.filter((i) => selIngs.includes(i.id));

  async function runQuick(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const c = await createConsultation({
        mode,
        ingredients_or_problem: problem,
        produce_lot_ids: selLots,
        ingredient_ids: selIngs,
        traceability: trace,
        service_context: ctx,
        allergens: allergens
          .split(/[,;\n]+/)
          .map((s) => s.trim())
          .filter(Boolean),
        desired_outcome: outcome,
        request_graph_recall: true,
      });
      setActive(c);
    } catch (ex) {
      if (ex instanceof AuthError) {
        onAuthLost?.();
        return;
      }
      setError(ex instanceof Error ? ex.message : "Could not run plan");
    } finally {
      setBusy(false);
    }
  }

  async function handoffNext() {
    if (!active?.local_safety_plan?.recommended_action) return;
    try {
      const res = await postCapture(
        `Evolving cook · ${active.mode} · ${active.local_safety_plan.recommended_action}`,
      );
      if (res.board) onBoard?.(res.board);
      setNote("Saved next action to Today");
    } catch (ex) {
      if (ex instanceof AuthError) onAuthLost?.();
      else setNote(ex instanceof Error ? ex.message : "save failed");
    }
  }

  if (fullOpen) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <button type="button" className="signout-btn" onClick={() => setFullOpen(false)}>
            ← Back to Evolving Cook
          </button>
          <span className="meta-dim font-mono text-xs uppercase">full Cook Studio</span>
        </div>
        <CookStudioWorkspace
          onBoard={onBoard}
          onAuthLost={onAuthLost}
          liveTask={liveTask}
          initialConsultation={active}
          embedded
        />
      </div>
    );
  }

  return (
    <section className="board-card" data-accent="green" aria-label="Evolving Cook">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="board-card-title" data-accent="green">
            evolving cook
          </h2>
          <p className="meta-dim m-0 text-sm leading-relaxed">
            Line entry for build, rescue, service & develop. Safety first — citations required for
            verified claims.
          </p>
        </div>
        <button type="button" className="signout-btn shrink-0" onClick={() => setFullOpen(true)}>
          Open full Cook Studio
        </button>
      </div>

      <div className="ec-route mt-3" aria-live="polite">
        {active ? (
          <>
            <div className="font-mono text-xs uppercase tracking-wide text-fg">
              {(active.mode || mode).toUpperCase()} · {active.title}
            </div>
            <div className="meta-dim mt-1 space-y-0.5 text-sm">
              <div>Safety checked {mark(pipe.safety)}</div>
              <div>Local plan ready {mark(pipe.local)}</div>
              <div>
                Kitchen memory{" "}
                {pipe.km === "queued"
                  ? "queued"
                  : pipe.km === "working"
                    ? "working"
                    : pipe.km === "returned"
                      ? "returned"
                      : pipe.km === "unavailable"
                        ? "unavailable"
                        : "not requested"}
              </div>
              <div className="text-fg">Next: {pipe.next}</div>
              <div>Updated: {rel(active.updated_at)}</div>
              {active.blocked_reason ? (
                <div className="level-warn">{active.blocked_reason}</div>
              ) : null}
            </div>
            <EvidenceStrip c={active} />
          </>
        ) : (
          <p className="meta-dim m-0 text-sm">No active consultation — start one below.</p>
        )}
      </div>

      <div className="mode-strip mt-3" role="tablist" aria-label="Cook mode">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={mode === m.id}
            className={`mode-chip ${mode === m.id ? "is-active" : ""}`}
            onClick={() => setMode(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>

      <form className="mt-1 flex flex-col gap-2" onSubmit={(e) => void runQuick(e)}>
        <label className="ec-label" htmlFor="ec-problem">
          {mode === "service"
            ? "Live problem"
            : mode === "develop"
              ? "Dish / direction"
              : mode === "build"
                ? "Build goal / ingredients"
                : "What is available"}
        </label>
        <textarea
          id="ec-problem"
          className="ec-input"
          rows={2}
          value={problem}
          onChange={(e) => setProblem(e.target.value)}
          placeholder={
            mode === "service"
              ? "Cold plate, ticket stack, allergen miss…"
              : mode === "develop"
                ? "Improve cost, flavour, allergen version…"
                : "onion ends, herb trim, chicken trim…"
          }
        />

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="ec-label">Traceability</label>
            <select
              className="ec-input"
              value={trace}
              onChange={(e) => setTrace(e.target.value as typeof trace)}
            >
              {TRACE.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="ec-label">Service</label>
            <select
              className="ec-input"
              value={ctx}
              onChange={(e) => setCtx(e.target.value as typeof ctx)}
            >
              {CTX.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <label className="ec-label">Allergens · outcome</label>
        <div className="grid grid-cols-2 gap-2">
          <input
            className="ec-input"
            placeholder="celery, gluten…"
            value={allergens}
            onChange={(e) => setAllergens(e.target.value)}
          />
          <input
            className="ec-input"
            placeholder="staff soup, hash…"
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
          />
        </div>

        {(produce.length > 0 || ingredients.length > 0) && (
          <div className="ec-route">
            <div className="ec-label mb-1">From stock (optional)</div>
            <div className="flex max-h-24 flex-wrap gap-x-3 gap-y-1 overflow-y-auto text-sm">
              {produce.slice(0, 8).map((p) => (
                <label key={p.id} className="meta-dim flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={selLots.includes(p.id)}
                    onChange={() =>
                      setSelLots((s) =>
                        s.includes(p.id) ? s.filter((x) => x !== p.id) : [...s, p.id],
                      )
                    }
                  />
                  {p.name}
                </label>
              ))}
              {ingredients.slice(0, 8).map((i) => (
                <label key={i.id} className="meta-dim flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={selIngs.includes(i.id)}
                    onChange={() =>
                      setSelIngs((s) =>
                        s.includes(i.id) ? s.filter((x) => x !== i.id) : [...s, i.id],
                      )
                    }
                  />
                  {i.name}
                </label>
              ))}
            </div>
          </div>
        )}

        <button type="submit" className="login-btn" disabled={busy}>
          {busy ? "Planning…" : "Run plan"}
        </button>
      </form>

      {error ? (
        <div className="level-warn mt-2 text-sm" role="alert">
          {error}
        </div>
      ) : null}

      {active?.local_safety_plan ? (
        <div className="mt-3 flex flex-col gap-2">
          <div>
            <div className="ec-step">Safety</div>
            <div className="text-sm font-medium text-fg">{verdictText(active)}</div>
            <p className="meta-dim m-0 mt-0.5 text-sm">
              {active.local_safety_plan.decision.summary}
            </p>
          </div>
          {(selectedProduce.length > 0 || selectedIngs.length > 0) && (
            <div>
              <div className="ec-step">Selected stock</div>
              <p className="meta-dim m-0 text-sm">
                {[
                  ...selectedProduce.map((p) => p.name),
                  ...selectedIngs.map((i) => i.name),
                ]
                  .filter(Boolean)
                  .slice(0, 6)
                  .join(" · ") || "—"}
              </p>
            </div>
          )}
          <div>
            <div className="ec-step">Next action</div>
            <p className="m-0 text-sm text-fg">{pipe.next}</p>
            <div className="meta-dim mt-1 text-xs">
              Kitchen memory: {kmLabel(pipe.km)}
              {pipe.km === "queued" || pipe.km === "working"
                ? " — not claimed live until worker verified"
                : pipe.km === "unavailable"
                  ? " — local plan stands"
                  : ""}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="signout-btn" onClick={() => void handoffNext()}>
              Save next to Today
            </button>
            <button type="button" className="signout-btn" onClick={() => setFullOpen(true)}>
              Open full Cook Studio
            </button>
          </div>
          {note ? (
            <div className="status-ok text-sm" role="status">
              {note}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="board-card-footer">
        evidence-gated · Graph Recall not claimed live · research never auto-canonical
      </div>
    </section>
  );
}
