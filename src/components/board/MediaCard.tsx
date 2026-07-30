import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MediaSection, PlayState, Track } from "@/lib/board-types";

const FALLBACK_TRACK_S = 48;

function formatTime(sec: number) {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

export function MediaCard({
  media,
  onMedia,
  runCommand,
}: {
  media: MediaSection;
  onMedia: (m: MediaSection) => void;
  runCommand: (command: string, payload?: Record<string, unknown>) => Promise<string>;
}) {
  const [elapsed, setElapsed] = useState(0);
  const [flash, setFlash] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const mediaRef = useRef(media);
  mediaRef.current = media;

  const notify = useCallback((msg: string) => setFlash(msg), []);

  useEffect(() => {
    if (!flash) return;
    const id = window.setTimeout(() => setFlash(null), 1800);
    return () => window.clearTimeout(id);
  }, [flash]);

  useEffect(() => {
    setElapsed(0);
  }, [media.current?.id]);

  const trackLen = media.current?.duration_s ?? FALLBACK_TRACK_S;

  useEffect(() => {
    if (media.state !== "playing") return;
    const id = window.setInterval(() => {
      setElapsed((e) => {
        const len = mediaRef.current.current?.duration_s ?? FALLBACK_TRACK_S;
        return e + 1 >= len ? 0 : e + 1;
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, [media.state, media.current?.id]);

  async function run(command: string, payload: Record<string, unknown> = {}) {
    if (busy) return;
    setBusy(true);
    try {
      const note = await runCommand(command, payload);
      notify(note || command);
    } finally {
      setBusy(false);
    }
  }

  const track: Track | null = media.current;
  const progress = Math.min(1, elapsed / Math.max(1, trackLen));
  const stateClass =
    media.state === "playing"
      ? "media-state-playing"
      : media.state === "paused"
        ? "media-state-paused"
        : "media-state-idle";

  const statusLine = useMemo(() => {
    if (media.state === "playing" && track) {
      return `mirror · ${formatTime(elapsed)} / ${formatTime(trackLen)}`;
    }
    if (media.state === "paused" && track) {
      return `paused · ${formatTime(elapsed)} / ${formatTime(trackLen)}`;
    }
    return `idle · hosted state`;
  }, [media.state, track, elapsed, trackLen]);

  return (
    <section className="board-card" data-accent="peach" aria-label="media">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h2 className="board-card-title" data-accent="peach">
          media
        </h2>
        <div className="flex items-center gap-2 flex-wrap">
          {media.cassette ? (
            <span className="cassette-badge" title={media.cassette_repo}>
              cassette · ffmpeg
            </span>
          ) : null}
          <span className={`media-state-chip ${stateClass}`}>{media.state}</span>
        </div>
      </div>

      <div className="media-path">
        <span className="media-path-step" data-on="true">
          {media.fetcher}
        </span>
        <span className="media-path-arrow">→</span>
        <span className="media-path-step" data-on="true">
          {media.player}
        </span>
        <span className="media-path-arrow">→</span>
        <span
          className="media-path-step"
          data-on={media.cassette ? "true" : "false"}
          data-cassette={media.cassette ? "true" : "false"}
        >
          {media.cassette ? media.cassette_engine : "bypass"}
        </span>
        <span className="media-path-arrow">→</span>
        <span className="media-path-step" data-on="true">
          out
        </span>
      </div>

      <div className="media-now">
        <div className="media-now-top">
          <span className={`media-eq ${media.state === "playing" ? "is-on" : ""}`} aria-hidden>
            <i />
            <i />
            <i />
            <i />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-fg truncate">
              {track ? (
                <>
                  {track.title}
                  <span className="meta-dim"> · {track.artist}</span>
                </>
              ) : (
                <span className="meta-dim">no track</span>
              )}
            </div>
            <div className="font-mono text-xs text-muted mt-0.5 tabular">{statusLine}</div>
          </div>
        </div>
        <div className="media-progress" role="progressbar" aria-valuenow={elapsed}>
          <div
            className={`media-progress-fill ${media.state === "playing" ? "is-playing" : ""}`}
            style={{ width: `${progress * 100}%` }}
          />
        </div>
        <div className="media-progress-meta font-mono text-xs text-faint tabular">
          <span>{formatTime(elapsed)}</span>
          <span>{media.note || "hosted mirror"}</span>
          <span>{formatTime(trackLen)}</span>
        </div>
      </div>

      <ul className="m-0 list-none p-0 text-sm text-muted">
        {media.queue.slice(0, 5).map((t, i) => (
          <li key={t.id} className="item-row py-1 flex items-baseline gap-2">
            <span className="font-mono text-faint tabular shrink-0 w-4">{i + 1}</span>
            <span className="truncate">
              {t.title}
              <span className="meta-dim"> · {t.artist}</span>
            </span>
            {i === 0 ? <span className="tag-chip shrink-0">up next</span> : null}
          </li>
        ))}
      </ul>

      <div className="media-controls">
        <button type="button" data-active={media.state === "playing"} disabled={busy} onClick={() => void run("media_play")}>
          Play
        </button>
        <button type="button" data-active={media.state === "paused"} disabled={busy} onClick={() => void run("media_pause")}>
          Pause
        </button>
        <button type="button" disabled={busy} onClick={() => void run("media_next")}>
          Next
        </button>
        <button type="button" data-active={media.state === "idle"} disabled={busy} onClick={() => void run("media_stop")}>
          Stop
        </button>
        <button
          type="button"
          data-active={media.cassette}
          disabled={busy}
          onClick={() => void run(media.cassette ? "media_cassette_off" : "media_cassette_on")}
        >
          Cassette
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void run("media_volume", { volume: Math.max(0, media.volume - 5) })}
        >
          Vol −
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void run("media_volume", { volume: Math.min(100, media.volume + 5) })}
        >
          Vol +
        </button>
      </div>

      <div className="media-flash font-mono text-xs" aria-live="polite">
        {flash ?? "\u00a0"}
      </div>

      <div className="board-card-footer">
        {media.playlist_label} · {media.path_label} · vol {media.volume}
      </div>
    </section>
  );
}
