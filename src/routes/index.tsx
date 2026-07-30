import { createFileRoute } from "@tanstack/react-router";
import { CasualBoard } from "@/components/board/CasualBoard";

export const Route = createFileRoute("/")({
  component: Home,
});

function Home() {
  return <CasualBoard />;
}
