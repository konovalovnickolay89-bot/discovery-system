import { useCallback, useEffect, useState } from "react";
import type { Board } from "@/lib/board-types";
import { AuthError, postCapture } from "@/lib/board-api";
import {
  completeConsultation,
  createConsultation,
  createIngredient,
  createProduce,
  getConsultation,
  listConsultations,
  listDishes,
  listIngredients,
  listProduce,
  saveDishFromConsultation,
  type CookConsultation,
  type Dish,
  type Ingredient,
  type ProduceLot,
} from "@/lib/cook-api";

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

function statusLabel(s: string) {
  return s.replace(/_/g, " ");
}

function grLabel(s: string) {
  if (s === "not_requested") return "local plan only";
  if (s === "queued") return "queued";
  if (s === "leased") return "working";
  if (s === "completed") return "returned";
  if (s === "failed") return "unavailable / failed";
  return s;
}

/** Full Cook Studio workspace — opened from Kitchen Ops. */
export function CookStudioWorkspace({
  onBoard,
  onAuthLost,
  liveTask,
  initialConsultation = null,
  embedded = false,
  initialDrawer = "closed",
}: {
  onBoard?: (b: Board) => void;
  onAuthLost?: () => void;
  liveTask?: Record<string, unknown> | null;
  initialConsultation?: CookConsultation | null;
  embedded?: boolean;
  initialDrawer?: "closed" | "produce" | "ingredients" | "dishes";
}) {
  const [mode, setMode] = useState<(typeof MODES)[number]["id"]>("rescue");
  const [problem, setProblem] = useState("");
  const [trace, setTrace] = useState<(typeof TRACE)[number]["value"]>("labelled_chilled_known");
  const [ctx, setCtx] = useState<(typeof CTX)[number]["value"]>("staff_meal");
  const [allergens, setAllergens] = useState("");
  const [outcome, setOutcome] = useState("");
  const [portions, setPortions] = useState("");
  const [minutes, setMinutes] = useState("");
  const [equipment, setEquipment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<CookConsultation | null>(initialConsultation);
  const [history, setHistory] = useState<CookConsultation[]>([]);
  const [produce, setProduce] = useState<ProduceLot[]>([]);
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [dishes, setDishes] = useState<Dish[]>([]);
  const [selLots, setSelLots] = useState<string[]>([]);
  const [selIngs, setSelIngs] = useState<string[]>([]);
  const [drawer, setDrawer] = useState<"closed" | "produce" | "ingredients" | "dishes">(
    initialDrawer,
  );
  const [note, setNote] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [studioTab, setStudioTab] = useState<"service" | "stock" | "consult" | "history">(
    initialDrawer === "produce" ? "stock" : "consult",
  );

  const loadLib = useCallback(async () => {
    try {
      const [p, i, d, h] = await Promise.all([
        listProduce(),
        listIngredients(),
        listDishes(),
        listConsultations(false),
      ]);
      setProduce(p);
      setIngredients(i);
      setDishes(d);
      setHistory(h.slice(0, 8));
    } catch (e) {
      if (e instanceof AuthError) onAuthLost?.();
    }
  }, [onAuthLost]);

  useEffect(() => {
    void loadLib();
  }, [loadLib]);

  useEffect(() => {
    if (initialConsultation) setActive(initialConsultation);
  }, [initialConsultation]);

  useEffect(() => {
    setDrawer(initialDrawer);
    if (initialDrawer === "produce") setStudioTab("stock");
  }, [initialDrawer]);

  useEffect(() => {
    if (!liveTask?.id || typeof liveTask.id !== "string") return;
    void getConsultation(liveTask.id)
      .then(setActive)
      .catch(() => undefined);
  }, [liveTask]);

  async function run(e: React.FormEvent) {
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
        covers_or_portions: portions ? Number(portions) : null,
        time_available_minutes: minutes ? Number(minutes) : null,
        equipment: equipment
          .split(/[,;\n]+/)
          .map((s) => s.trim())
          .filter(Boolean),
        desired_outcome: outcome,
        request_graph_recall: true,
      });
      setActive(c);
      setHistory((h) => [c, ...h.filter((x) => x.id !== c.id)].slice(0, 8));
    } catch (ex) {
      if (ex instanceof AuthError) {
        onAuthLost?.();
        return;
      }
      setError(ex instanceof Error ? ex.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  async function refreshActive() {
    if (!active) return;
    try {
      setActive(await getConsultation(active.id));
    } catch (e) {
      if (e instanceof AuthError) onAuthLost?.();
    }
  }

  async function saveDish() {
    if (!active) return;
    try {
      const d = await saveDishFromConsultation(active.id);
      setNote(`Saved draft dish: ${d.name}`);
      void loadLib();
    } catch (e) {
      if (e instanceof AuthError) onAuthLost?.();
      else setNote(e instanceof Error ? e.message : "save failed");
    }
  }

  async function markDone() {
    if (!active) return;
    try {
      setActive(await completeConsultation(active.id));
      setNote("Marked for review");
    } catch (e) {
      if (e instanceof AuthError) onAuthLost?.();
    }
  }

  async function captureNext() {
    if (!active?.local_safety_plan?.recommended_action) return;
    try {
      const res = await postCapture(
        `Cook Studio · ${active.mode} · ${active.local_safety_plan.recommended_action}`,
      );
      if (res.board) onBoard?.(res.board);
      setNote("Captured to Today");
    } catch (e) {
      if (e instanceof AuthError) onAuthLost?.();
    }
  }

  async function addProduce() {
    if (!newName.trim()) return;
    try {
      await createProduce({ name: newName.trim(), quantity: 1, unit: "kg" });
      setNewName("");
      void loadLib();
    } catch (e) {
      if (e instanceof AuthError) onAuthLost?.();
    }
  }

  async function addIngredient() {
    if (!newName.trim()) return;
    try {
      await createIngredient({ name: newName.trim() });
      setNewName("");
      void loadLib();
    } catch (e) {
      if (e instanceof AuthError) onAuthLost?.();
    }
  }

  const plan = active?.local_safety_plan;
  const shell = embedded ? "flex flex-col gap-3" : "board-card";

  return (
    <section
      className={shell}
      data-accent={embedded ? undefined : "green"}
      aria-label="Cook Studio"
    >
      {!embedded ? (
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="board-card-title" data-accent="green">
              cook studio
            </h2>
            <p className="meta-dim m-0 text-sm">
              Professional kitchen workspace · stock · enquiries · evidence
            </p>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="board-card-title m-0" data-accent="green">
            cook studio
          </h2>
          <span className="ko-chip">
            {(active?.service_context || ctx).replace(/_/g, " ")} · graph recall ·{" "}
            {active ? grLabel(active.graph_recall_status) : "idle"}
          </span>
        </div>
      )}

      <div className="mode-strip" role="tablist" aria-label="Studio sections">
        {(
          [
            ["service", "Service"],
            ["stock", "Stock"],
            ["consult", "Consult"],
            ["history", "Duties / history"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={studioTab === id}
            className={`mode-chip ${studioTab === id ? "is-active" : ""}`}
            onClick={() => {
              setStudioTab(id);
              if (id === "stock") setDrawer("produce");
              else setDrawer("closed");
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {studioTab === "service" && active ? (
        <div className="ec-route space-y-2 text-sm">
          <div className="ec-step">Service board · active enquiry</div>
          <div className="font-medium text-fg">
            {active.mode.toUpperCase()} · {active.title}
          </div>
          <div className="meta-dim">
            State: {statusLabel(active.task_status)} · Graph Recall:{" "}
            {grLabel(active.graph_recall_status)}
          </div>
          <div>
            <div className="ec-step">Next physical action</div>
            <p className="m-0 text-fg">
              {plan?.recommended_action || active.blocked_reason || "—"}
            </p>
          </div>
          {plan?.decision ? (
            <div>
              <div className="ec-step">Local safety</div>
              <p className="m-0">
                {String(plan.decision.verdict || "").replace(/_/g, " ")} — {plan.decision.summary}
              </p>
              {plan.rejected ? (
                <p className="level-warn m-0 mt-1 text-sm">
                  Recommendation withheld. A blocked local safety decision cannot be overridden by
                  Kitchen memory — escalate or discard.
                </p>
              ) : null}
            </div>
          ) : null}
          <button type="button" className="signout-btn" onClick={() => void refreshActive()}>
            Refresh task
          </button>
        </div>
      ) : null}

      {studioTab === "stock" || drawer !== "closed" ? (
        <div className="ec-route">
          <div className="flex flex-wrap gap-2">
            {(["produce", "ingredients", "dishes"] as const).map((d) => (
              <button
                key={d}
                type="button"
                className={`mode-chip ${drawer === d ? "is-active" : ""}`}
                onClick={() => setDrawer(d)}
              >
                {d}
              </button>
            ))}
            <button type="button" className="mode-chip" onClick={() => setDrawer("closed")}>
              close
            </button>
          </div>
          {drawer === "produce" ? (
            <div className="mt-2 space-y-2 text-sm">
              {produce.slice(0, 12).map((p) => (
                <label key={p.id} className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={selLots.includes(p.id)}
                    onChange={() =>
                      setSelLots((s) =>
                        s.includes(p.id) ? s.filter((x) => x !== p.id) : [...s, p.id],
                      )
                    }
                  />
                  <span>
                    <strong>{p.name}</strong>
                    <span className="meta-dim">
                      {" "}
                      · {p.quantity}
                      {p.unit} · {p.storage_location} · {p.traceability?.replace(/_/g, " ")}
                    </span>
                  </span>
                </label>
              ))}
              <div className="flex gap-2">
                <input
                  className="ec-input"
                  placeholder="Receive lot name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
                <button type="button" className="signout-btn" onClick={() => void addProduce()}>
                  receive lot
                </button>
              </div>
            </div>
          ) : null}
          {drawer === "ingredients" ? (
            <div className="mt-2 space-y-2 text-sm">
              {ingredients.slice(0, 12).map((ing) => (
                <label key={ing.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selIngs.includes(ing.id)}
                    onChange={() =>
                      setSelIngs((s) =>
                        s.includes(ing.id) ? s.filter((x) => x !== ing.id) : [...s, ing.id],
                      )
                    }
                  />
                  {ing.name}
                </label>
              ))}
              <div className="flex gap-2">
                <input
                  className="ec-input"
                  placeholder="New ingredient"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
                <button type="button" className="signout-btn" onClick={() => void addIngredient()}>
                  add
                </button>
              </div>
            </div>
          ) : null}
          {drawer === "dishes" ? (
            <ul className="mt-2 m-0 list-none space-y-1 p-0 text-sm">
              {dishes.slice(0, 12).map((d) => (
                <li key={d.id}>
                  <strong>{d.name}</strong>
                  <span className="meta-dim">
                    {" "}
                    · {d.type} · {d.status}
                  </span>
                </li>
              ))}
              {!dishes.length ? <li className="meta-dim">No dishes yet</li> : null}
            </ul>
          ) : null}
        </div>
      ) : null}

      {studioTab === "consult" ? (
        <>
          <div className="mode-strip" role="tablist" aria-label="Cook mode">
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

          <form className="flex flex-col gap-2" onSubmit={(e) => void run(e)}>
            <label className="ec-label">Problem / ingredients / goal</label>
            <textarea
              className="ec-input"
              rows={2}
              value={problem}
              onChange={(e) => setProblem(e.target.value)}
              placeholder="What is on the pass or in the fridge…"
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
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <input
                className="ec-input"
                placeholder="allergens"
                value={allergens}
                onChange={(e) => setAllergens(e.target.value)}
              />
              <input
                className="ec-input"
                placeholder="covers"
                value={portions}
                onChange={(e) => setPortions(e.target.value)}
              />
              <input
                className="ec-input"
                placeholder="minutes"
                value={minutes}
                onChange={(e) => setMinutes(e.target.value)}
              />
              <input
                className="ec-input"
                placeholder="equipment"
                value={equipment}
                onChange={(e) => setEquipment(e.target.value)}
              />
            </div>
            <input
              className="ec-input"
              placeholder="Desired outcome"
              value={outcome}
              onChange={(e) => setOutcome(e.target.value)}
            />
            <button type="submit" className="login-btn" disabled={busy}>
              {busy ? "Planning…" : "Run plan · queue Kitchen memory"}
            </button>
          </form>
        </>
      ) : null}

      {error ? (
        <div className="level-warn text-sm" role="alert">
          {error}
        </div>
      ) : null}

      {active && (studioTab === "consult" || studioTab === "service") ? (
        <div className="flex flex-col gap-2">
          <div className="ec-route">
            <div className="font-mono text-xs uppercase text-fg">
              {active.mode} · {statusLabel(active.task_status)}
            </div>
            <div className="meta-dim text-sm">
              Graph Recall: {grLabel(active.graph_recall_status)} · {active.title}
            </div>
            {plan ? (
              <>
                <div className="mt-2 text-sm font-medium text-fg">
                  {plan.decision?.title} — {String(plan.decision?.verdict || "").replace(/_/g, " ")}
                </div>
                <p className="meta-dim m-0 text-sm">{plan.decision?.summary}</p>
                <p className="m-0 mt-1 text-sm text-fg">{plan.recommended_action}</p>
                {plan.evidence_gate_status ? (
                  <div className="meta-dim mt-2 text-sm">
                    Evidence: {plan.evidence_source_count ?? 0} sources
                    {plan.evidence_best_tier != null ? ` · best T${plan.evidence_best_tier}` : ""}
                    {" · "}
                    {plan.evidence_verified
                      ? "verified"
                      : plan.evidence_gate_status.replace(/_/g, " ")}
                  </div>
                ) : null}
                {plan.kitchen_memory?.length ? (
                  <ul className="mt-2 m-0 list-disc pl-4 text-sm">
                    {plan.kitchen_memory.map((m, i) => (
                      <li key={i}>
                        {m.title}
                        {m.path ? (
                          <span className="meta-dim font-mono text-xs"> · {m.path}</span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {plan.notes?.length ? (
                  <ul className="meta-dim m-0 mt-1 list-disc pl-4 text-xs">
                    {plan.notes.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                ) : null}
              </>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="signout-btn" onClick={() => void refreshActive()}>
              Refresh
            </button>
            <button type="button" className="signout-btn" onClick={() => void captureNext()}>
              → Today
            </button>
            <button type="button" className="signout-btn" onClick={() => void saveDish()}>
              Save dish draft
            </button>
            <button type="button" className="signout-btn" onClick={() => void markDone()}>
              Mark complete
            </button>
          </div>
          {note ? (
            <div className="status-ok text-sm" role="status">
              {note}
            </div>
          ) : null}
        </div>
      ) : null}

      {studioTab === "history" ? (
        <div>
          <div className="ec-step">Recent enquiries · duties</div>
          <ul className="m-0 list-none space-y-1 p-0 text-sm">
            {history.map((h) => (
              <li key={h.id}>
                <button
                  type="button"
                  className="signout-btn w-full text-left"
                  onClick={() => {
                    setActive(h);
                    setStudioTab("service");
                  }}
                >
                  {h.mode} · {h.title} · {statusLabel(h.task_status)}
                  {h.local_safety_plan?.evidence_gate_status
                    ? ` · evidence ${h.local_safety_plan.evidence_gate_status.replace(/_/g, " ")}`
                    : ""}
                </button>
              </li>
            ))}
            {!history.length ? <li className="meta-dim">No history yet</li> : null}
          </ul>
        </div>
      ) : null}

      {!embedded ? (
        <div className="board-card-footer">
          cook studio · evidence gate final · Graph Recall not claimed live
        </div>
      ) : null}
    </section>
  );
}

/** Standalone card (legacy) — prefer Kitchen Ops on the board. */
export function CookStudioCard(props: {
  onBoard?: (b: Board) => void;
  onAuthLost?: () => void;
  liveTask?: Record<string, unknown> | null;
}) {
  return <CookStudioWorkspace {...props} />;
}
