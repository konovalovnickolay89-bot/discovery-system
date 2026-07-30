import { useState } from "react";
import type { Board } from "@/lib/board-types";
import { postChat } from "@/lib/board-api";

/** Hermes / Linux-Wiki panel — allowlisted board commands only, never shell. */
export function ChatPanel({
  board,
  onBoard,
}: {
  board: Board;
  onBoard: (b: Board) => void;
}) {
  const [msg, setMsg] = useState("");
  const [log, setLog] = useState<{ role: "you" | "hermes"; text: string }[]>([
    {
      role: "hermes",
      text: "Allowlisted ops only: status · capture <note> · add/remind <text>. No shell.",
    },
  ]);
  const [busy, setBusy] = useState(false);

  async function send() {
    if (!msg.trim() || busy) return;
    const text = msg.trim();
    setMsg("");
    setLog((l) => [...l, { role: "you", text }]);
    setBusy(true);
    try {
      const res = await postChat(text);
      setLog((l) => [...l, { role: "hermes", text: res.reply }]);
      if (res.board) onBoard(res.board);
    } catch (e) {
      setLog((l) => [
        ...l,
        { role: "hermes", text: e instanceof Error ? e.message : "chat failed" },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="board-card" data-accent="blue" aria-label="hermes chat">
      <h2 className="board-card-title" data-accent="blue">
        hermes · linux-wiki
      </h2>
      <p className="meta-dim m-0 text-sm">
        Maintainer channel · board rev {board.meta.revision} · no unrestricted shell
      </p>
      <div className="chat-log">
        {log.map((line, i) => (
          <div key={i} className={`chat-line chat-${line.role}`}>
            <span className="font-mono text-xs text-faint">{line.role}</span>
            <div>{line.text}</div>
          </div>
        ))}
      </div>
      <div className="ai-panel">
        <textarea
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          placeholder="status · capture defrost pastry · remind walk-in 06:30"
          rows={2}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <div className="ai-actions">
          <button
            type="button"
            className="primary"
            disabled={busy || !msg.trim()}
            onClick={() => void send()}
            style={{
              borderColor: "color-mix(in oklab, var(--color-blue) 45%, var(--color-border))",
              background: "color-mix(in oklab, var(--color-blue) 12%, var(--color-surface-2))",
              color: "var(--color-blue)",
            }}
          >
            {busy ? "sending…" : "send"}
          </button>
        </div>
      </div>
      <div className="board-card-footer">allowlist only · audit via /v1/actions</div>
    </section>
  );
}
