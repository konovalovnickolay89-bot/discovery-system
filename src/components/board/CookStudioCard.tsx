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

/** Full Cook Studio workspace — opened from Evolving Cook. */
export function CookStudioWorkspace({
  onBoard,
  onAuthLost,
  liveTask,
  initialConsultation = null,
  embedded = false,
}: {
  onBoard?: (b: Board) => void;
  onAuthLost?: () => void;
  liveTask?: Record<string, unknown> | null;
  initialConsultation?: CookConsultation | null;
  embedded?: boolean;
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
  const [drawer, setDrawer] = useState<"closed" | "produce" | "ingredients" | "dishes">("closed");
  const [note, setNote] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

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
    if (!liveTask?.id || typeof liveTask.id !== "string") return;
    void getConsultation(liveTask.id)
      .then((c) => {
        setActive(c);
        setHistory((h) => {
          const rest = h.filter((x) => x.id !== c.id);
          return [c, ...rest].slice(0, 8);
        });
      })
      .catch(() => undefined);
  }, [liveTask]);

  async function runConsult(e: React.FormEvent) {
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
      setError(ex instanceof Error ? ex.message : "Could not run Cook Studio");
    } finally {
      setBusy(false);
    }
  }

  async function handoff(text: string) {
    try {
      const res = await postCapture(`Cook Studio · ${text}`);
      if (res.board) onBoard?.(res.board);
      setNote("Saved to Today");
    } catch (ex) {
      if (ex instanceof AuthError) onAuthLost?.();
      else setNote(ex instanceof Error ? ex.message : "save failed");
    }
  }

  const plan = active?.local_safety_plan;

  return (
    <section className="board-card" data-accent="green" aria-label="Cook Studio full">
      <div className="flex items-start justify-between gap-2">
        <h2 className="board-card-title" data-accent="green">
          {embedded ? "cook studio · full" : "cook studio"}
        </h2>
        <button
          type="button"
          className="signout-btn"
          onClick={() => setDrawer(drawer === "closed" ? "produce" : "closed")}
        >
          {drawer === "closed" ? "stock · library" : "close library"}
        </button>
      </div>

      <div className="mode-strip" role="tablist" aria-label="Cook Studio mode">
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

      {drawer !== "closed" ? (
        <div className="ec-route mt-2">
          <div className="mode-strip mb-2">
            {(["produce", "ingredients", "dishes"] as const).map((t) => (
              <button
                key={t}
                type="button"
                className={`mode-chip ${drawer === t ? "is-active" : ""}`}
                onClick={() => setDrawer(t)}
              >
                {t}
              </button>
            ))}
          </div>
          {drawer === "produce" ? (
            <div className="flex flex-col gap-2">
              <ul className="m-0 list-none p-0 text-sm">
                {produce.map((p) => (
                  <li key={p.id} className="meta-dim flex justify-between gap-2 py-0.5">
                    <label className="flex gap-2">
                      <input
                        type="checkbox"
                        checked={selLots.includes(p.id)}
                        onChange={() =>
                          setSelLots((s) =>
                            s.includes(p.id) ? s.filter((x) => x !== p.id) : [...s, p.id],
                          )
                        }
                      />
                      {p.name} · {p.quantity}
                      {p.unit} · {p.status}
                    </label>
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                <input
                  className="ec-input"
                  placeholder="New produce name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
                <button
                  type="button"
                  className="signout-btn"
                  onClick={() => {
                    if (!newName.trim()) return;
                    void createProduce({
                      name: newName.trim(),
                      quantity: 1,
                      unit: "kg",
                      storage_location: "fridge",
                      traceability: "labelled_chilled_known",
                    })
                      .then(() => {
                        setNewName("");
                        return loadLib();
                      })
                      .catch((e) => setError(String(e)));
                  }}
                >
                  add
                </button>
              </div>
            </div>
          ) : null}
          {drawer === "ingredients" ? (
            <div className="flex flex-col gap-2">
              <ul className="m-0 list-none p-0 text-sm">
                {ingredients.map((i) => (
                  <li key={i.id} className="meta-dim flex gap-2 py-0.5">
                    <label className="flex gap-2">
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
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                <input
                  className="ec-input"
                  placeholder="New ingredient"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
                <button
                  type="button"
                  className="signout-btn"
                  onClick={() => {
                    if (!newName.trim()) return;
                    void createIngredient({ name: newName.trim() })
                      .then(() => {
                        setNewName("");
                        return loadLib();
                      })
                      .catch((e) => setError(String(e)));
                  }}
                >
                  add
                </button>
              </div>
            </div>
          ) : null}
          {drawer === "dishes" ? (
            <ul className="m-0 list-none p-0 text-sm">
              {dishes.map((d) => (
                <li key={d.id} className="meta-dim py-0.5">
                  {d.name} · {d.type} · {d.status}
                </li>
              ))}
              {!dishes.length ? <li className="meta-dim">No dishes yet</li> : null}
            </ul>
          ) : null}
        </div>
      ) : null}

      <form className="mt-3 flex flex-col gap-2.5" onSubmit={(e) => void runConsult(e)}>
        <label className="ec-label" htmlFor="cs-problem">
          {mode === "service"
            ? "Live problem"
            : mode === "develop"
              ? "Dish / direction"
              : "Ingredients or problem"}
        </label>
        <textarea
          id="cs-problem"
          className="ec-input"
          rows={3}
          value={problem}
          onChange={(e) => setProblem(e.target.value)}
          placeholder={
            mode === "rescue"
              ? "onion ends, herb stalks, chicken trim…"
              : mode === "service"
                ? "Ticket stack, cold plate, allergen miss…"
                : "Describe the dish or build goal…"
          }
        />

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

        <label className="ec-label">Service context</label>
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

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="ec-label">Portions / covers</label>
            <input
              className="ec-input"
              inputMode="numeric"
              value={portions}
              onChange={(e) => setPortions(e.target.value)}
            />
          </div>
          <div>
            <label className="ec-label">Time (min)</label>
            <input
              className="ec-input"
              inputMode="numeric"
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
            />
          </div>
        </div>

        <label className="ec-label">Allergens</label>
        <input
          className="ec-input"
          value={allergens}
          onChange={(e) => setAllergens(e.target.value)}
          placeholder="celery, gluten…"
        />

        <label className="ec-label">Equipment</label>
        <input
          className="ec-input"
          value={equipment}
          onChange={(e) => setEquipment(e.target.value)}
          placeholder="combi, salamander…"
        />

        <label className="ec-label">Desired outcome</label>
        <input className="ec-input" value={outcome} onChange={(e) => setOutcome(e.target.value)} />

        <button type="submit" className="login-btn" disabled={busy}>
          {busy ? "Working…" : "Run Cook Studio"}
        </button>
      </form>

      {error ? (
        <div className="level-warn mt-3 text-sm" role="alert">
          {error}
        </div>
      ) : null}

      {active && plan ? (
        <div className="ec-plan mt-4 flex flex-col gap-3">
          <div className="ec-route">
            <div className="font-mono text-xs uppercase text-muted">
              {active.mode} · {active.title}
            </div>
            <div className="meta-dim text-sm">
              Task: {statusLabel(active.task_status)} · Kitchen memory:{" "}
              {grLabel(active.graph_recall_status)}
            </div>
          </div>

          <div>
            <div className="ec-step">1 · Safety / feasibility</div>
            <div className="text-sm font-medium text-fg">
              {plan.decision.verdict.replace(/_/g, " ")} — {plan.decision.title}
            </div>
            <p className="meta-dim m-0 mt-1 text-sm">{plan.decision.summary}</p>
          </div>

          {plan.rejected ? (
            <div>
              <div className="ec-step">Disposal / escalation</div>
              <ul className="m-0 list-disc pl-4 text-sm">
                {plan.disposal_checklist.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </div>
          ) : (
            <>
              <div>
                <div className="ec-step">2 · Recommended action now</div>
                <p className="m-0 text-sm">{plan.recommended_action}</p>
              </div>
              <div>
                <div className="ec-step">3 · Primary plan</div>
                <div className="text-sm font-medium">{String(plan.primary_plan.title || "Plan")}</div>
                <p className="meta-dim m-0 text-sm">{String(plan.primary_plan.summary || "")}</p>
                <ul className="m-0 mt-1 list-disc pl-4 text-sm">
                  {((plan.primary_plan.steps as string[]) || []).map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="ec-step">4 · Alternatives</div>
                {plan.alternatives.map((a) => (
                  <div key={a.title} className="ec-route mb-2">
                    <div className="text-sm font-medium">{a.title}</div>
                    <p className="meta-dim m-0 text-sm">{a.summary}</p>
                  </div>
                ))}
              </div>
              <div>
                <div className="ec-step">5 · Mise · method · hold · pass · recovery</div>
                <ul className="m-0 list-none p-0 text-sm">
                  <li>
                    <span className="text-muted">Purpose · </span>
                    {plan.recipe_spine.purpose}
                  </li>
                  <li>
                    <span className="text-muted">Mise · </span>
                    {plan.recipe_spine.mise}
                  </li>
                  <li>
                    <span className="text-muted">Method · </span>
                    {plan.recipe_spine.method}
                  </li>
                  <li>
                    <span className="text-muted">Hold · </span>
                    {plan.recipe_spine.holding_regeneration}
                  </li>
                  <li>
                    <span className="text-muted">Pass · </span>
                    {plan.recipe_spine.pass_finish}
                  </li>
                  <li>
                    <span className="text-muted">Recovery · </span>
                    {plan.recipe_spine.failure_recovery}
                  </li>
                </ul>
              </div>
              <div>
                <div className="ec-step">6 · Allergen & service checks</div>
                <ul className="m-0 list-disc pl-4 text-sm">
                  {[...plan.allergen_checks, ...plan.service_checks].map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="ec-step">7 · Kitchen memory</div>
                {plan.kitchen_memory?.length ? (
                  <ul className="m-0 list-disc pl-4 text-sm">
                    {plan.kitchen_memory.map((m) => (
                      <li key={m.title + m.path}>
                        <strong>{m.title}</strong>
                        {m.path ? ` · ${m.path}` : ""}
                        {m.relevance ? ` — ${m.relevance}` : ""}
                        {m.excerpt ? <div className="meta-dim">{m.excerpt}</div> : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="meta-dim m-0 text-sm">
                    {active.graph_recall_status === "queued" ||
                    active.graph_recall_status === "leased"
                      ? "Kitchen memory pending — local plan is ready."
                      : active.graph_recall_status === "failed"
                        ? "Kitchen memory unavailable — local plan only."
                        : "Local plan only (Kitchen memory not requested or not returned)."}
                  </p>
                )}
                <p className="meta-dim m-0 mt-1 text-xs">
                  Graph Recall is not claimed live until a worker is verified.
                </p>
              </div>
            </>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="signout-btn"
              onClick={() => void handoff(`${active.title}: ${plan.recommended_action}`)}
            >
              Save to Today
            </button>
            {!plan.rejected ? (
              <button
                type="button"
                className="signout-btn"
                onClick={() =>
                  void saveDishFromConsultation(active.id, active.title)
                    .then(() => setNote("Saved as dish draft"))
                    .catch((e) => setNote(String(e)))
                }
              >
                Save as dish
              </button>
            ) : null}
            <button
              type="button"
              className="signout-btn"
              onClick={() =>
                void completeConsultation(active.id)
                  .then((c) => setActive(c))
                  .catch((e) => setNote(String(e)))
              }
            >
              Mark reviewed
            </button>
          </div>
          {note ? (
            <div className="status-ok text-sm" role="status">
              {note}
            </div>
          ) : null}

          {active.audit?.length ? (
            <div>
              <div className="ec-step">Audit</div>
              <ul className="meta-dim m-0 list-none p-0 text-xs">
                {active.audit.slice(-6).map((a, i) => (
                  <li key={i}>
                    {a.event}
                    {a.at ? ` · ${new Date(a.at).toLocaleString()}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      {history.length ? (
        <div className="mt-4">
          <div className="ec-step">Recent</div>
          <ul className="m-0 list-none p-0">
            {history.map((h) => (
              <li key={h.id}>
                <button
                  type="button"
                  className="signout-btn mb-1 w-full text-left"
                  onClick={() =>
                    void getConsultation(h.id)
                      .then(setActive)
                      .catch((e) => setError(String(e)))
                  }
                >
                  {h.mode.toUpperCase()} · {h.title} · {statusLabel(h.task_status)}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="board-card-footer">
        full workspace · stock, dishes, history · Graph Recall not claimed live
      </div>
    </section>
  );
}
