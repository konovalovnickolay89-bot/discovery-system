/**
 * Kitchen Ops — dashboard surface for Cook Studio (design: evolving cook · kitchen ops).
 * Compact ops card; full Cook Studio opens as the detailed workspace.
 */
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

type StudioTab = "consult" | "stock" | "duties";

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

function planOf(c: CookConsultation | null) {
  return c?.local_safety_plan;
}

function pipeline(c: CookConsultation | null) {
  if (!c) {
    return {
      safety: false,
      local: false,
      km: "none" as const,
      next: "Select mode and open a consultation",
    };
  }
  const ts = c.task_status;
  const gr = c.graph_recall_status;
  const safety = ts !== "draft";
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

function serviceChip(ctx: string) {
  return (ctx || "undecided").replace(/_/g, " ");
}

function isRiskLot(p: ProduceLot) {
  const t = p.traceability || "";
  const st = p.status || "";
  return (
    t === "unknown" ||
    t === "guest_exposed_buffet" ||
    st === "quarantined" ||
    st === "waste"
  );
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
  else if (c.graph_recall_status === "completed")
    statusLine = "Kitchen memory returned — not auto-verified";

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
        {statusLine ? (
          <div className={verified ? "status-ok" : "level-warn"}>{statusLine}</div>
        ) : null}
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

/** @deprecated name kept for imports — renders Kitchen Ops */
export function EvolvingCookCard(props: {
  onBoard?: (b: Board) => void;
  onAuthLost?: () => void;
  liveTask?: Record<string, unknown> | null;
  activeTasks?: Array<Partial<CookConsultation> & { id: string }>;
}) {
  return <KitchenOpsCard {...props} />;
}

export function KitchenOpsCard({
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
  const [history, setHistory] = useState<CookConsultation[]>([]);
  const [produce, setProduce] = useState<ProduceLot[]>([]);
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [selLots, setSelLots] = useState<string[]>([]);
  const [selIngs, setSelIngs] = useState<string[]>([]);
  const [fullOpen, setFullOpen] = useState(false);
  const [studioFocus, setStudioFocus] = useState<StudioTab>("consult");
  const [note, setNote] = useState<string | null>(null);
  const [showQuick, setShowQuick] = useState(false);

  const loadLib = useCallback(async () => {
    try {
      const [p, i, h] = await Promise.all([
        listProduce(),
        listIngredients(),
        listConsultations(false),
      ]);
      setProduce(p);
      setIngredients(i);
      setHistory(h.slice(0, 12));
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

  const stats = useMemo(() => {
    const risk = produce.filter(isRiskLot).length;
    const enquiriesLive = history.filter((c) =>
      ["kitchen_memory_queued", "kitchen_memory_working", "local_plan_ready"].includes(
        c.task_status,
      ),
    ).length;
    const dutiesOpen = history.filter((c) =>
      ["needs_review", "blocked", "kitchen_memory_returned"].includes(c.task_status),
    ).length;
    const evidenceAwait = history.filter((c) => {
      const g = c.local_safety_plan?.evidence_gate_status;
      const r = c.local_safety_plan?.evidence_research_status;
      return (
        g === "insufficient_evidence" ||
        g === "pending_review" ||
        r === "pending_review" ||
        c.task_status === "needs_review"
      );
    }).length;
    return {
      risk,
      dutiesOpen: dutiesOpen + (active && ["needs_review", "blocked", "kitchen_memory_returned"].includes(active.task_status) && !history.some((h) => h.id === active.id) ? 1 : 0),
      enquiriesLive:
        enquiriesLive +
        (active &&
        ["kitchen_memory_queued", "kitchen_memory_working"].includes(active.task_status) &&
        !history.some((h) => h.id === active.id)
          ? 1
          : 0),
      evidenceAwait,
    };
  }, [produce, history, active]);

  const alertLines = useMemo(() => {
    const lines: string[] = [];
    produce.filter(isRiskLot).slice(0, 3).forEach((p) => {
      lines.push(`Stock risk · ${p.name} (${(p.traceability || p.status).replace(/_/g, " ")})`);
    });
    if (active?.task_status === "blocked") {
      lines.push(`Blocked · ${active.title}`);
    }
    if (pipe.km === "unavailable") lines.push("Kitchen memory unavailable — local plan stands");
    return lines.slice(0, 4);
  }, [produce, active, pipe.km]);

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
      setShowQuick(false);
      void loadLib();
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
    if (!active?.local_safety_plan?.recommended_action && !pipe.next) return;
    try {
      const res = await postCapture(
        `Kitchen ops · ${active?.mode || mode} · ${active?.local_safety_plan?.recommended_action || pipe.next}`,
      );
      if (res.board) onBoard?.(res.board);
      setNote("Saved next action to Today");
    } catch (ex) {
      if (ex instanceof AuthError) onAuthLost?.();
      else setNote(ex instanceof Error ? ex.message : "save failed");
    }
  }

  function openStudio(tab: StudioTab = "consult") {
    setStudioFocus(tab);
    setFullOpen(true);
  }

  if (fullOpen) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button type="button" className="signout-btn" onClick={() => setFullOpen(false)}>
            ← Back to kitchen ops
          </button>
          <span className="meta-dim font-mono text-xs uppercase">
            cook studio · {studioFocus}
            {active ? ` · graph recall · ${active.graph_recall_status.replace(/_/g, " ")}` : ""}
          </span>
        </div>
        <CookStudioWorkspace
          onBoard={onBoard}
          onAuthLost={onAuthLost}
          liveTask={liveTask}
          initialConsultation={active}
          embedded
          initialDrawer={
            studioFocus === "stock"
              ? "produce"
              : studioFocus === "duties"
                ? "closed"
                : "closed"
          }
        />
      </div>
    );
  }

  const activeLabel = active
    ? `${(active.mode || "").toUpperCase()} · ${active.title}`
    : "No active consultation";
  const safetyLine = active?.local_safety_plan?.decision
    ? `${String(active.local_safety_plan.decision.verdict || "").replace(/_/g, " ")}${
        active.local_safety_plan.decision.title
          ? ` — ${active.local_safety_plan.decision.title}`
          : ""
      }`
    : "—";

  return (
    <section className="board-card" data-accent="green" aria-label="Kitchen ops">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="board-card-title" data-accent="green">
            evolving cook · kitchen ops
          </h2>
          <p className="meta-dim m-0 text-sm leading-relaxed">
            Line ops for stock, duties and Cook Studio enquiries. Safety first — citations for
            verified claims.
          </p>
        </div>
        <span className="ko-chip shrink-0" title="Service context">
          {serviceChip(active?.service_context || ctx)}
        </span>
      </div>

      <div className="ko-stats mt-3" role="group" aria-label="Kitchen ops counts">
        <div className="ko-stat">
          <div className="ko-stat-n">{stats.risk}</div>
          <div className="ko-stat-l">stock at risk</div>
        </div>
        <div className="ko-stat">
          <div className="ko-stat-n">{stats.dutiesOpen}</div>
          <div className="ko-stat-l">duties open</div>
        </div>
        <div className="ko-stat">
          <div className="ko-stat-n">{stats.enquiriesLive}</div>
          <div className="ko-stat-l">enquiries live</div>
        </div>
        <div className="ko-stat">
          <div className="ko-stat-n">{stats.evidenceAwait}</div>
          <div className="ko-stat-l">awaiting review</div>
        </div>
      </div>

      <div className="ec-route mt-3" aria-live="polite">
        <div className="ec-step">Active task</div>
        <div className="text-sm font-medium text-fg">{activeLabel}</div>
        {active ? (
          <div className="meta-dim mt-1 space-y-0.5 text-sm">
            <div>
              Safety {pipe.safety ? "checked" : "—"} · Local plan {pipe.local ? "ready" : "—"} ·
              Kitchen memory {pipe.km === "none" ? "not requested" : pipe.km}
            </div>
            <div className="text-fg">
              <span className="ec-step inline">Next physical action</span>
              <div className="mt-0.5 font-normal normal-case tracking-normal">{pipe.next}</div>
            </div>
            <div>Updated: {rel(active.updated_at)}</div>
            {active.blocked_reason ? (
              <div className="level-warn">{active.blocked_reason}</div>
            ) : null}
            <div className="meta-dim">Safety: {safetyLine}</div>
          </div>
        ) : (
          <p className="meta-dim m-0 mt-1 text-sm">
            No live enquiry — consult from here or open Cook Studio.
          </p>
        )}
        {active ? <EvidenceStrip c={active} /> : null}
      </div>

      {alertLines.length > 0 ? (
        <ul className="ko-alerts mt-2 m-0 list-none p-0">
          {alertLines.map((a) => (
            <li key={a} className="ko-alert-line">
              {a}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mode-strip mt-3" role="tablist" aria-label="Cook mode">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={mode === m.id}
            className={`mode-chip ${mode === m.id ? "is-active" : ""}`}
            onClick={() => {
              setMode(m.id);
              setShowQuick(true);
            }}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        <button type="button" className="signout-btn" onClick={() => openStudio("consult")}>
          open cook studio
        </button>
        <button type="button" className="signout-btn" onClick={() => openStudio("stock")}>
          stock
        </button>
        <button type="button" className="signout-btn" onClick={() => openStudio("duties")}>
          duties
        </button>
        <button
          type="button"
          className="signout-btn"
          onClick={() => {
            setShowQuick((v) => !v);
            setStudioFocus("consult");
          }}
        >
          consult
        </button>
        {active ? (
          <button type="button" className="signout-btn" onClick={() => void handoffNext()}>
            save next to Today
          </button>
        ) : null}
      </div>

      {showQuick ? (
        <form className="mt-3 flex flex-col gap-2" onSubmit={(e) => void runQuick(e)}>
          <label className="ec-label" htmlFor="ko-problem">
            {mode === "service"
              ? "Live problem"
              : mode === "develop"
                ? "Dish / direction"
                : mode === "build"
                  ? "Build goal / ingredients"
                  : "What is available"}
          </label>
          <textarea
            id="ko-problem"
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
          <div className="grid grid-cols-2 gap-2">
            <input
              className="ec-input"
              placeholder="allergens…"
              value={allergens}
              onChange={(e) => setAllergens(e.target.value)}
            />
            <input
              className="ec-input"
              placeholder="desired outcome…"
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
      ) : null}

      {error ? (
        <div className="level-warn mt-2 text-sm" role="alert">
          {error}
        </div>
      ) : null}
      {note ? (
        <div className="status-ok mt-2 text-sm" role="status">
          {note}
        </div>
      ) : null}

      <div className="board-card-footer">
        kitchen ops · evidence-gated · Graph Recall not claimed live
      </div>
    </section>
  );
}
