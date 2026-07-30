import { useState } from "react";
import { AuthError, postCapture, postEvolvingCook, type EvolvingCookPlan } from "@/lib/board-api";
import type { Board } from "@/lib/board-types";

const TRACE = [
  { value: "labelled_chilled_known", label: "Labelled, chilled & known" },
  { value: "clean_raw_trim", label: "Clean raw trim" },
  { value: "unknown", label: "Unknown" },
  { value: "guest_exposed_buffet", label: "Guest-exposed buffet" },
] as const;

const WHERE = [
  { value: "canteen", label: "Canteen" },
  { value: "staff_meal", label: "Staff meal" },
  { value: "breakfast", label: "Breakfast" },
  { value: "banqueting", label: "Banqueting" },
  { value: "a_la_carte", label: "À la carte" },
  { value: "home", label: "Home" },
  { value: "undecided", label: "Undecided" },
] as const;

function verdictClass(v: string) {
  if (v === "proceed") return "status-ok";
  if (v === "caution") return "status-warn";
  return "level-warn";
}

function verdictLabel(v: string) {
  if (v === "proceed") return "Proceed";
  if (v === "caution") return "Caution";
  return "Discard or escalate";
}

export function EvolvingCookCard({
  onBoard,
  onAuthLost,
}: {
  onBoard?: (b: Board) => void;
  onAuthLost?: () => void;
}) {
  const [available, setAvailable] = useState("");
  const [traceability, setTraceability] =
    useState<(typeof TRACE)[number]["value"]>("labelled_chilled_known");
  const [whereFor, setWhereFor] = useState<(typeof WHERE)[number]["value"]>("staff_meal");
  const [allergens, setAllergens] = useState("");
  const [outcome, setOutcome] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<EvolvingCookPlan | null>(null);
  const [handoffNote, setHandoffNote] = useState<string | null>(null);

  async function makeRoutes(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setHandoffNote(null);
    try {
      const res = await postEvolvingCook({
        available,
        traceability,
        where_for: whereFor,
        allergens,
        desired_outcome: outcome,
      });
      setPlan(res);
    } catch (ex) {
      if (ex instanceof AuthError) {
        onAuthLost?.();
        return;
      }
      setError(ex instanceof Error ? ex.message : "Could not plan routes");
      setPlan(null);
    } finally {
      setBusy(false);
    }
  }

  async function saveHandoff(kind: string, text: string) {
    setHandoffNote(null);
    try {
      const res = await postCapture(`Evolving cook · ${kind}: ${text}`);
      if (res.board) onBoard?.(res.board);
      setHandoffNote(`Saved to Today · ${kind}`);
    } catch (ex) {
      if (ex instanceof AuthError) {
        onAuthLost?.();
        return;
      }
      setHandoffNote(ex instanceof Error ? ex.message : "Save failed");
    }
  }

  return (
    <section className="board-card" data-accent="green" aria-label="Evolving cook">
      <h2 className="board-card-title" data-accent="green">
        evolving cook
      </h2>
      <p className="meta-dim m-0 mb-3 text-sm leading-relaxed">
        Surplus & trim planner. Safety first — unknown or guest-exposed food is never suggested
        for guest service.
      </p>

      <form className="flex flex-col gap-2.5" onSubmit={(e) => void makeRoutes(e)}>
        <label className="ec-label" htmlFor="ec-available">
          What is available
        </label>
        <textarea
          id="ec-available"
          className="ec-input"
          rows={3}
          placeholder="onion ends, herb stalks, chicken trim…"
          value={available}
          onChange={(e) => setAvailable(e.target.value)}
        />

        <label className="ec-label" htmlFor="ec-trace">
          Traceability
        </label>
        <select
          id="ec-trace"
          className="ec-input"
          value={traceability}
          onChange={(e) => setTraceability(e.target.value as (typeof TRACE)[number]["value"])}
        >
          {TRACE.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>

        <label className="ec-label" htmlFor="ec-where">
          Where is it for
        </label>
        <select
          id="ec-where"
          className="ec-input"
          value={whereFor}
          onChange={(e) => setWhereFor(e.target.value as (typeof WHERE)[number]["value"])}
        >
          {WHERE.map((w) => (
            <option key={w.value} value={w.value}>
              {w.label}
            </option>
          ))}
        </select>

        <label className="ec-label" htmlFor="ec-all">
          Allergens to carry forward
        </label>
        <input
          id="ec-all"
          className="ec-input"
          placeholder="celery, gluten, milk…"
          value={allergens}
          onChange={(e) => setAllergens(e.target.value)}
        />

        <label className="ec-label" htmlFor="ec-out">
          Desired outcome
        </label>
        <input
          id="ec-out"
          className="ec-input"
          placeholder="quick staff soup, breakfast hash…"
          value={outcome}
          onChange={(e) => setOutcome(e.target.value)}
        />

        <button type="submit" className="login-btn" disabled={busy}>
          {busy ? "Planning…" : "Make safe routes"}
        </button>
      </form>

      {error ? (
        <div className="level-warn mt-3 text-sm" role="alert">
          {error}
        </div>
      ) : null}

      {plan ? (
        <div className="ec-plan mt-4 flex flex-col gap-3">
          <div>
            <div className="ec-step">1 · First decision</div>
            <div className={`font-medium ${verdictClass(plan.decision.verdict)}`}>
              {verdictLabel(plan.decision.verdict)} — {plan.decision.title}
            </div>
            <p className="meta-dim m-0 mt-1 text-sm">{plan.decision.summary}</p>
            {!plan.guest_service_allowed ? (
              <p className="level-warn m-0 mt-1 text-sm">
                Guest service not allowed on this plan.
              </p>
            ) : null}
          </div>

          <div>
            <div className="ec-step">2 · Do this next</div>
            <p className="m-0 text-sm text-fg">{plan.do_this_next}</p>
            <button
              type="button"
              className="signout-btn mt-2"
              onClick={() => void saveHandoff("next", plan.do_this_next)}
            >
              Save a hand-off to Today
            </button>
          </div>

          <div>
            <div className="ec-step">3 · Three routes</div>
            <div className="flex flex-col gap-2">
              {plan.routes.map((r) => (
                <div key={r.id} className="ec-route">
                  <div className="font-mono text-xs uppercase text-muted">
                    {r.title}
                    {!r.guest_service ? " · not guest" : ""}
                  </div>
                  <div className="text-sm">{r.summary}</div>
                  <ul className="meta-dim m-0 mt-1 list-disc pl-4 text-sm">
                    {r.steps.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                  <button
                    type="button"
                    className="signout-btn mt-2"
                    onClick={() =>
                      void saveHandoff(r.title, `${r.summary} · ${r.steps.join(" · ")}`)
                    }
                  >
                    Save a hand-off to Today
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="ec-step">4 · Sort the tray</div>
            <div className="ec-sort grid gap-2">
              <SortCol title="Use now" items={plan.sort_tray.use_now} />
              <SortCol title="Prep later" items={plan.sort_tray.prep_later} />
              <SortCol title="Store" items={plan.sort_tray.store} />
              <SortCol title="Stop or escalate" items={plan.sort_tray.stop_or_escalate} danger />
            </div>
          </div>

          <div>
            <div className="ec-step">5 · Sensory & allergens</div>
            <ul className="meta-dim m-0 list-disc pl-4 text-sm">
              {plan.sensory_checks.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
            <ul className="m-0 mt-2 list-disc pl-4 text-sm text-fg">
              {plan.allergen_prompts.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
            <button
              type="button"
              className="signout-btn mt-2"
              onClick={() =>
                void saveHandoff(
                  "allergens",
                  plan.allergen_prompts.join(" · ") || "check allergens",
                )
              }
            >
              Save a hand-off to Today
            </button>
          </div>

          {handoffNote ? (
            <div className="status-ok text-sm" role="status">
              {handoffNote}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="board-card-footer">safety-first · no guest path for unknown / buffet-exposed</div>
    </section>
  );
}

function SortCol({
  title,
  items,
  danger,
}: {
  title: string;
  items: string[];
  danger?: boolean;
}) {
  return (
    <div className={`ec-sort-col ${danger ? "is-danger" : ""}`}>
      <div className="font-mono text-xs uppercase text-muted">{title}</div>
      {items.length ? (
        <ul className="m-0 mt-1 list-none p-0 text-sm">
          {items.map((i) => (
            <li key={i} className="meta-dim">
              · {i}
            </li>
          ))}
        </ul>
      ) : (
        <div className="meta-dim text-sm">—</div>
      )}
    </div>
  );
}
