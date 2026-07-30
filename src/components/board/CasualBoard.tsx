import { useCallback, useEffect, useState } from "react";
import type { Board, HealthResponse, MediaSection } from "@/lib/board-types";
import {
  AuthError,
  connectBoardSocket,
  fetchBoard,
  fetchHealth,
  isSignedIn,
  logout,
  postCommand,
} from "@/lib/board-api";
import { FALLBACK_BOARD } from "@/lib/board-fallback";
import { validateApiConfig } from "@/lib/api-config";
import { HeaderBar } from "./HeaderBar";
import { TodayCard } from "./TodayCard";
import { MediaCard } from "./MediaCard";
import { EvolvingCookCard } from "./EvolvingCookCard";
import { LearningCard } from "./LearningCard";
import { listConsultations, type CookConsultation } from "@/lib/cook-api";
import { BriefingCard } from "./BriefingCard";
import { MachineCard } from "./MachineCard";
import { ChatPanel } from "./ChatPanel";
import { BoardSettings } from "./BoardSettings";
import { ApiFailureBanner, type ApiFailureKind } from "./ApiFailureBanner";
import { LoginPanel } from "./LoginPanel";

export function CasualBoard() {
  const [authed, setAuthed] = useState(false);
  const [board, setBoard] = useState<Board>(FALLBACK_BOARD);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [connection, setConnection] = useState("connecting…");
  const [failure, setFailure] = useState<ApiFailureKind | null>(null);
  const [failureDetail, setFailureDetail] = useState<string | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [authNote, setAuthNote] = useState<string | null>(null);
  const [cookTasks, setCookTasks] = useState<
    Array<Partial<CookConsultation> & { id: string }>
  >([]);
  const [liveCook, setLiveCook] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    setAuthed(isSignedIn());
  }, []);

  const onBoard = useCallback((b: Board) => {
    setBoard(b);
    setLoadedOnce(true);
    setFailure((f) => (f === "unreachable" || f === "offline-cache" ? null : f));
  }, []);

  const load = useCallback(async () => {
    const cfg = validateApiConfig();
    if (!cfg.ok) {
      setFailure("misconfigured");
      setFailureDetail(cfg.reason);
      setConnection("misconfigured");
      return;
    }
    try {
      const [b, h] = await Promise.all([fetchBoard(), fetchHealth()]);
      setHealth(h);
      setBoard(b);
      setLoadedOnce(true);
      setFailure(null);
      setAuthNote(null);
      try {
        const active = await listConsultations(true);
        setCookTasks(active);
      } catch {
        /* optional until cook API deployed */
      }
    } catch (e) {
      if (e instanceof AuthError) {
        setAuthed(false);
        setAuthNote("Session expired — sign in again.");
        return;
      }
      setFailure("unreachable");
      setFailureDetail(e instanceof Error ? e.message : "API unreachable");
      setConnection("api unreachable");
    }
  }, []);

  useEffect(() => {
    if (!authed) return;
    void load();
  }, [authed, load]);

  useEffect(() => {
    if (!authed) return;
    const cfg = validateApiConfig();
    if (!cfg.ok) return;
    return connectBoardSocket({
      onBoard,
      onCookTask: (task) => {
        setLiveCook(task);
        setCookTasks((prev) => {
          const id = String(task.id || "");
          const rest = prev.filter((x) => x.id !== id);
          return [{ ...task, id }, ...rest].slice(0, 8);
        });
      },
      onStatus: (s) => {
        setConnection(s);
        if (s === "live") {
          setFailure((f) => (f === "unreachable" || f === "offline-cache" ? null : f));
        } else if (s.startsWith("reconnect") || s === "offline") {
          if (loadedOnce) setFailure("offline-cache");
          else setFailure("unreachable");
        }
      },
      onAuthError: () => {
        setAuthed(false);
        setAuthNote("Session expired — sign in again.");
      },
    });
  }, [authed, onBoard, loadedOnce]);

  if (!authed) {
    return (
      <>
        {authNote ? (
          <div className="app-shell" style={{ maxWidth: 420, marginBottom: 0 }}>
            <div className="api-failure-banner" data-kind="misconfigured" role="status">
              <div className="api-failure-title">signed out</div>
              <p className="api-failure-body">{authNote}</p>
            </div>
          </div>
        ) : null}
        <LoginPanel
          onSignedIn={() => {
            setAuthed(true);
            setAuthNote(null);
          }}
        />
      </>
    );
  }

  async function setMediaFromCommand(command: string, payload: Record<string, unknown> = {}) {
    try {
      const res = await postCommand(command, payload);
      if (res.board) setBoard(res.board);
      return res.action.message;
    } catch (e) {
      if (e instanceof AuthError) {
        setAuthed(false);
        setAuthNote("Session expired — sign in again.");
      }
      return e instanceof Error ? e.message : "command failed";
    }
  }

  return (
    <div className="app-shell">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="m-0 font-mono text-sm font-medium tracking-wide text-fg uppercase">
          Casual Board
        </h1>
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-faint">private · session</span>
          <button
            type="button"
            className="signout-btn"
            onClick={() => {
              logout();
              setAuthed(false);
              setBoard(FALLBACK_BOARD);
              setAuthNote(null);
            }}
          >
            sign out
          </button>
        </div>
      </div>

      <ApiFailureBanner kind={failure} detail={failureDetail} lastSync={board.meta.updated_at} />
      <HeaderBar meta={board.meta} health={health} connection={connection} />

      <div className="board-grid">
        <div className="board-col board-col-left flex flex-col gap-3.5">
          <TodayCard board={board} onBoard={setBoard} />
          <MediaCard
            media={board.media}
            onMedia={(m: MediaSection) => setBoard((b) => ({ ...b, media: m }))}
            runCommand={setMediaFromCommand}
          />
          <div className="hidden min-[1100px]:block">
            <MachineCard machine={board.machine} />
          </div>
        </div>
        <div className="board-col board-col-right flex flex-col gap-3.5">
          <EvolvingCookCard
            onBoard={setBoard}
            liveTask={liveCook}
            activeTasks={cookTasks}
            onAuthLost={() => {
              setAuthed(false);
              setAuthNote("Session expired — sign in again.");
            }}
          />
          <LearningCard board={board} />
          <BriefingCard briefing={board.briefing} />
          <ChatPanel board={board} onBoard={setBoard} />
          <BoardSettings
            board={board}
            onBoard={setBoard}
            onAuthLost={() => {
              setAuthed(false);
              setAuthNote("Session expired — sign in again.");
            }}
          />
          <div className="min-[1100px]:hidden">
            <MachineCard machine={board.machine} />
          </div>
        </div>
      </div>
    </div>
  );
}
