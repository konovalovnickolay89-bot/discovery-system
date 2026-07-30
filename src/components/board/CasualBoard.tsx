import { useCallback, useEffect, useState } from "react";
import type { Board, HealthResponse, MediaSection } from "@/lib/board-types";
import {
  connectBoardSocket,
  fetchBoard,
  fetchHealth,
  postCommand,
} from "@/lib/board-api";
import { FALLBACK_BOARD } from "@/lib/board-fallback";
import { validateApiConfig } from "@/lib/api-config";
import { HeaderBar } from "./HeaderBar";
import { TodayCard } from "./TodayCard";
import { MediaCard } from "./MediaCard";
import { LearningCard } from "./LearningCard";
import { BriefingCard } from "./BriefingCard";
import { MachineCard } from "./MachineCard";
import { ChatPanel } from "./ChatPanel";
import { ApiFailureBanner, type ApiFailureKind } from "./ApiFailureBanner";

export function CasualBoard() {
  const [board, setBoard] = useState<Board>(FALLBACK_BOARD);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [connection, setConnection] = useState("connecting…");
  const [failure, setFailure] = useState<ApiFailureKind | null>(null);
  const [failureDetail, setFailureDetail] = useState<string | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);

  const onBoard = useCallback((b: Board) => {
    setBoard(b);
    setLoadedOnce(true);
    setFailure((f) => (f === "unreachable" || f === "offline-cache" ? null : f));
  }, []);

  useEffect(() => {
    const cfg = validateApiConfig();
    if (!cfg.ok) {
      setFailure("misconfigured");
      setFailureDetail(cfg.reason);
      setConnection("misconfigured");
      return;
    }

    let cancelled = false;
    (async () => {
      const [b, h] = await Promise.all([fetchBoard(), fetchHealth()]);
      if (cancelled) return;
      if (h) {
        setHealth(h);
        if (b.meta.revision > 0) {
          setBoard(b);
          setLoadedOnce(true);
          setFailure(null);
        }
      } else {
        setHealth(null);
        setFailure(b.meta.revision > 0 ? "offline-cache" : "unreachable");
        setFailureDetail(
          "GET /health failed. Is FastAPI running and is VITE_API_BASE_URL correct?",
        );
        setConnection("api unreachable");
        if (b.meta.revision > 0) {
          setBoard(b);
          setLoadedOnce(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const cfg = validateApiConfig();
    if (!cfg.ok) return;
    return connectBoardSocket({
      onBoard,
      onStatus: (s) => {
        setConnection(s);
        if (s === "live") {
          setFailure((f) => (f === "unreachable" || f === "offline-cache" ? null : f));
        } else if (s.startsWith("reconnect") || s === "offline") {
          if (loadedOnce) setFailure("offline-cache");
          else setFailure("unreachable");
        }
      },
    });
  }, [onBoard, loadedOnce]);

  async function setMediaFromCommand(
    command: string,
    payload: Record<string, unknown> = {},
  ) {
    try {
      const res = await postCommand(command, payload);
      if (res.board) setBoard(res.board);
      return res.action.message;
    } catch (e) {
      return e instanceof Error ? e.message : "command failed";
    }
  }

  function setMediaLocal(media: MediaSection) {
    setBoard((b) => ({ ...b, media }));
  }

  return (
    <div className="app-shell">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="m-0 font-mono text-sm font-medium tracking-wide text-fg uppercase">
          Casual Board
        </h1>
        <span className="font-mono text-xs text-faint">
          discovery-system · public UI · debian bridge outbound
        </span>
      </div>

      <ApiFailureBanner
        kind={failure}
        detail={failureDetail}
        lastSync={board.meta.updated_at}
      />

      <HeaderBar meta={board.meta} health={health} connection={connection} />

      <div className="board-grid">
        <div className="board-col board-col-left flex flex-col gap-3.5">
          <TodayCard board={board} onBoard={setBoard} />
          <MediaCard
            media={board.media}
            onMedia={setMediaLocal}
            runCommand={setMediaFromCommand}
          />
          <div className="hidden min-[1100px]:block">
            <MachineCard machine={board.machine} />
          </div>
        </div>

        <div className="board-col board-col-right flex flex-col gap-3.5">
          <LearningCard board={board} />
          <BriefingCard briefing={board.briefing} />
          <ChatPanel board={board} onBoard={setBoard} />
          <div className="min-[1100px]:hidden">
            <MachineCard machine={board.machine} />
          </div>
        </div>
      </div>
    </div>
  );
}
