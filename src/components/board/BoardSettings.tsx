import { useState } from "react";
import type { Board } from "@/lib/board-types";
import { AuthError, postStartFresh } from "@/lib/board-api";

const PHRASE = "START FRESH";

function friendlyError(raw: string): string {
  const t = raw.toLowerCase();
  if (t.includes("not found") || t.includes("404")) {
    return (
      "API is still an older build (no /v1/board/start-fresh). " +
      "On Debian: git pull (commit 007c442+) and restart casual-board-api."
    );
  }
  if (t.includes("confirmation")) {
    return `Type exactly ${PHRASE} (all caps, one space).`;
  }
  return raw;
}

export function BoardSettings({
  board,
  onBoard,
  onAuthLost,
}: {
  board: Board;
  onBoard: (b: Board) => void;
  onAuthLost?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [phrase, setPhrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const canSubmit = phrase.trim() === PHRASE && !busy;

  async function runStartFresh(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    setOk(null);
    try {
      const res = await postStartFresh(phrase.trim());
      onBoard(res.board);
      setOk(
        res.message +
          (res.backup_path ? " · backup saved on API host" : "") +
          ` · rev ${res.board.meta.revision}`,
      );
      setPhrase("");
    } catch (ex) {
      if (ex instanceof AuthError) {
        onAuthLost?.();
        return;
      }
      setError(friendlyError(ex instanceof Error ? ex.message : "start fresh failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="board-card" data-accent="peach" aria-label="Board settings">
      <div className="flex items-start justify-between gap-2">
        <h2 className="board-card-title" data-accent="peach">
          board · settings
        </h2>
        <button type="button" className="signout-btn" onClick={() => setOpen((v) => !v)}>
          {open ? "close" : "manage"}
        </button>
      </div>

      {!open ? (
        <p className="meta-dim m-0 text-sm">
          Revision {board.meta.revision}. Destructive clear lives here — not automatic.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="meta-dim m-0 text-sm leading-relaxed">
            <strong className="text-fg">Start fresh</strong> clears{" "}
            <em>only</em> the live board content: Today, Media queue/track, Learning pool,
            Briefing pins/ring, and Machine snapshot (reset to “awaiting Debian”).
          </p>
          <ul className="meta-dim m-0 list-disc pl-4 text-sm leading-relaxed">
            <li>Keeps API config, Cloudflare tunnel, auth secrets, SQLite jobs, audit log</li>
            <li>Writes a timestamped backup of the current board.json on the API host</li>
            <li>Does not restore demo/seed chef content</li>
            <li>Uses your signed-in session only — never the owner/bridge token</li>
          </ul>

          <form className="flex flex-col gap-2" onSubmit={(e) => void runStartFresh(e)}>
            <label className="meta-dim font-mono text-xs uppercase" htmlFor="start-fresh-phrase">
              type {PHRASE} to confirm
            </label>
            <input
              id="start-fresh-phrase"
              className="login-input"
              autoComplete="off"
              spellCheck={false}
              value={phrase}
              onChange={(e) => setPhrase(e.target.value)}
              placeholder={PHRASE}
            />
            <button
              type="submit"
              className="danger-btn"
              disabled={!canSubmit}
              title={!canSubmit ? `Type ${PHRASE} exactly` : "Clear board content"}
            >
              {busy ? "clearing…" : "Start fresh"}
            </button>
          </form>

          {error ? (
            <div className="level-warn text-sm" role="alert">
              {error}
            </div>
          ) : null}
          {ok ? (
            <div className="status-ok text-sm" role="status">
              {ok}
            </div>
          ) : null}
        </div>
      )}
      <div className="board-card-footer">irreversible for live content · backup kept on API host</div>
    </section>
  );
}
