import type { CostRow } from "@/lib/types";

// Cost receipts as a monospace ledger (PRD §6.8 — "show the receipts").
export function CostBar({ rows }: { rows: CostRow[] }) {
  const total = rows.reduce((s, r) => s + r.cost_usd, 0);
  return (
    <div className="panel ticks">
      <span className="tick-bl" /><span className="tick-br" />
      <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-2">
        <span className="label kicker">$/goal — cost ledger</span>
        <span className="label">per-role routing</span>
      </div>
      <div className="px-4 py-3">
        {rows.length === 0 ? (
          <div className="mono text-xs text-[var(--text-dim)]">no cost recorded yet</div>
        ) : (
          <table className="w-full mono text-xs">
            <tbody>
              {rows.map((r) => (
                <tr key={r.agent_role} className="text-[var(--text-dim)]">
                  <td className="py-0.5 text-[var(--text)]">{r.agent_role}</td>
                  <td className="py-0.5 text-right tabular-nums">
                    {r.tokens_in}↓ / {r.tokens_out}↑
                  </td>
                  <td className="py-0.5 text-right">
                    {r.cached_tokens > 0 && (
                      <span className="text-[var(--ok)]">
                        {Math.round((r.cached_tokens / Math.max(r.tokens_in, 1)) * 100)}% cached
                      </span>
                    )}
                  </td>
                  <td className="py-0.5 text-right tabular-nums text-[var(--cyan)]">
                    ${r.cost_usd.toFixed(4)}
                  </td>
                </tr>
              ))}
              <tr className="border-t border-[var(--line)]">
                <td className="pt-1 label" colSpan={3}>
                  total
                </td>
                <td className="pt-1 text-right tabular-nums text-[var(--cyan)]">${total.toFixed(4)}</td>
              </tr>
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
