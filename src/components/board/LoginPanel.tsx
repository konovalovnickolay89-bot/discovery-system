import { useState } from "react";
import { login } from "@/lib/board-api";

export function LoginPanel({ onSignedIn }: { onSignedIn: () => void }) {
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(password);
      onSignedIn();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell" style={{ maxWidth: 420 }}>
      <h1 className="m-0 font-mono text-sm font-medium tracking-wide text-fg uppercase">
        Casual Board
      </h1>
      <p className="meta-dim mt-2 mb-4">
        Private personal board. Sign in to load data. Owner/bridge secrets never ship to this UI.
      </p>
      <form className="board-card" data-accent="peach" onSubmit={(e) => void submit(e)}>
        <h2 className="board-card-title" data-accent="peach">
          sign in
        </h2>
        <label className="meta-dim text-xs font-mono uppercase">UI password</label>
        <input
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="login-input"
          placeholder="CASUAL_BOARD_UI_PASSWORD"
        />
        {err ? <div className="level-warn text-sm">{err}</div> : null}
        <button type="submit" className="login-btn" disabled={busy || !password}>
          {busy ? "signing in…" : "sign in"}
        </button>
        <div className="board-card-footer">session is short-lived · stored only in this browser tab</div>
      </form>
    </div>
  );
}
