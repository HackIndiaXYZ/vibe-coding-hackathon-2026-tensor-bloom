import type { CostRow } from "@/lib/types";

export function CostBar({ rows }: { rows: CostRow[] }) {
  const total = rows.reduce((s, r) => s + r.cost_usd, 0);
  if (rows.length === 0) {
    return <div className="text-xs text-neutral-500">No cost recorded yet.</div>;
  }
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {rows.map((r) => (
        <span key={r.agent_role} className="rounded bg-neutral-100 px-2 py-1 dark:bg-neutral-800">
          <span className="font-medium">{r.agent_role}</span>{" "}
          <span className="text-neutral-500">${r.cost_usd.toFixed(4)}</span>
          {r.cached_tokens > 0 && (
            <span className="ml-1 text-emerald-600">
              {Math.round((r.cached_tokens / Math.max(r.tokens_in, 1)) * 100)}% cached
            </span>
          )}
        </span>
      ))}
      <span className="rounded bg-black px-2 py-1 font-semibold text-white dark:bg-white dark:text-black">
        = ${total.toFixed(4)}
      </span>
    </div>
  );
}
