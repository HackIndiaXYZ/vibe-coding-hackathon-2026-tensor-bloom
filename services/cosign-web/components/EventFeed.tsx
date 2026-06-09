import type { SSEEvent } from "@/lib/types";

const ICON: Record<string, string> = {
  "task.started": "▸",
  "task.tool_call": "⚙",
  "task.completed": "✓",
  "iteration.implementer": "✎",
  "iteration.critic": "⚖",
  "gate.pending": "✋",
  "goal.completed": "◆",
  "goal.failed": "✗",
  "goal.cancelled": "⊘",
};

const COLOR: Record<string, string> = {
  "iteration.implementer": "var(--cyan)",
  "iteration.critic": "var(--warn)",
  "gate.pending": "var(--warn)",
  "goal.completed": "var(--ok)",
  "goal.failed": "var(--danger)",
  "goal.cancelled": "var(--danger)",
};

// Live agent log rendered as a schematic trace; newest lines draw in.
export function EventFeed({ events }: { events: SSEEvent[] }) {
  if (events.length === 0) {
    return <div className="mono text-xs text-[var(--text-dim)] pulse">awaiting trace…</div>;
  }
  return (
    <ul className="mono text-xs">
      {events.map((e, i) => (
        <li key={`${e.id}-${i}`} className="rise flex gap-2 py-0.5" style={{ animationDelay: "0ms" }}>
          <span className="w-4 text-center" style={{ color: COLOR[e.event] ?? "var(--text-dim)" }}>
            {ICON[e.event] ?? "·"}
          </span>
          <span className="text-[var(--text-dim)]">{e.event}</span>
          <span className="truncate text-[var(--text)]">{summarize(e)}</span>
        </li>
      ))}
    </ul>
  );
}

function summarize(e: SSEEvent): string {
  const d = e.data;
  if (e.event === "iteration.implementer") return `r${d.round} · score ${d.self_satisfaction}`;
  if (e.event === "iteration.critic") return `r${d.round} · score ${d.score}`;
  if (e.event === "task.started") return String(d.role ?? "");
  if (e.event === "goal.completed" && d.output_url) return String(d.output_url);
  return "";
}
