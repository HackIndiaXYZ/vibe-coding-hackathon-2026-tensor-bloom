import type { SSEEvent } from "@/lib/types";

const ICON: Record<string, string> = {
  "task.started": "▶",
  "task.tool_call": "🔧",
  "task.completed": "✓",
  "iteration.implementer": "✎",
  "iteration.critic": "⚖",
  "gate.pending": "✋",
  "goal.completed": "🎉",
  "goal.failed": "✗",
  "goal.cancelled": "⊘",
};

export function EventFeed({ events }: { events: SSEEvent[] }) {
  if (events.length === 0) {
    return <div className="text-sm text-neutral-500">Waiting for events…</div>;
  }
  return (
    <ul className="space-y-1 font-mono text-xs">
      {events.map((e, i) => (
        <li key={`${e.id}-${i}`} className="flex gap-2">
          <span className="w-4 text-center">{ICON[e.event] ?? "•"}</span>
          <span className="text-neutral-500">{e.event}</span>
          <span className="truncate text-neutral-700 dark:text-neutral-300">
            {summarize(e)}
          </span>
        </li>
      ))}
    </ul>
  );
}

function summarize(e: SSEEvent): string {
  const d = e.data;
  if (e.event === "iteration.implementer") return `round ${d.round} · score ${d.self_satisfaction}`;
  if (e.event === "iteration.critic") return `round ${d.round} · score ${d.score}`;
  if (e.event === "task.started") return String(d.role ?? "");
  if (e.event === "goal.completed" && d.output_url) return String(d.output_url);
  return "";
}
