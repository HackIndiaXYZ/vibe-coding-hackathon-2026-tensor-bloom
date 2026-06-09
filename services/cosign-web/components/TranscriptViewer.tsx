import type { CriticIteration } from "@/lib/types";
import { DiffViewer } from "./DiffViewer";
import { Meter } from "./blueprint/Stat";

// The iteration transcript (PRD §6.7) — the artifact you actually cosign.
export function TranscriptViewer({ rounds }: { rounds: CriticIteration[] }) {
  if (rounds.length === 0) {
    return <div className="mono text-xs text-[var(--text-dim)]">no iterations yet</div>;
  }
  return (
    <div className="space-y-2">
      {rounds.map((r) => {
        const fb = (r.critic_feedback ?? {}) as Record<string, unknown>;
        const blocking = (fb.blocking_issues as string[]) ?? [];
        const suggestions = (fb.suggestions as string[]) ?? [];
        return (
          <details key={r.round_number} className="panel ticks group">
            <span className="tick-bl" /><span className="tick-br" />
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-2.5">
              <span className="mono text-sm">
                <span className="text-[var(--cyan)]">round {r.round_number}</span>
                <span className="ml-2 text-[var(--text-faint)] group-open:hidden">▸ expand</span>
                <span className="ml-2 hidden text-[var(--text-faint)] group-open:inline">▾ collapse</span>
              </span>
              <Meter value={r.self_satisfaction ?? 0} />
            </summary>
            <div className="space-y-3 border-t border-[var(--line)] p-4">
              <DiffViewer diff={r.implementer_diff} />
              {(blocking.length > 0 || suggestions.length > 0) && (
                <div className="mono text-xs">
                  {blocking.length > 0 && (
                    <div className="mb-2">
                      <div className="label" style={{ color: "var(--danger)" }}>blocking</div>
                      <ul className="mt-1 space-y-0.5 text-[var(--text)]">
                        {blocking.map((b, i) => <li key={i}>— {b}</li>)}
                      </ul>
                    </div>
                  )}
                  {suggestions.length > 0 && (
                    <div>
                      <div className="label" style={{ color: "var(--warn)" }}>suggestions</div>
                      <ul className="mt-1 space-y-0.5 text-[var(--text-dim)]">
                        {suggestions.map((s, i) => <li key={i}>— {s}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}
