import type { CriticIteration } from "@/lib/types";
import { DiffViewer } from "./DiffViewer";

function Bar({ value }: { value?: number }) {
  const pct = Math.round((value ?? 0) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-32 rounded bg-neutral-200 dark:bg-neutral-700">
        <div
          className="h-2 rounded bg-emerald-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-neutral-500">{(value ?? 0).toFixed(2)}</span>
    </div>
  );
}

export function TranscriptViewer({ rounds }: { rounds: CriticIteration[] }) {
  if (rounds.length === 0) {
    return <div className="text-sm text-neutral-500">No iterations yet.</div>;
  }
  return (
    <div className="space-y-2">
      {rounds.map((r) => {
        const fb = (r.critic_feedback ?? {}) as Record<string, unknown>;
        const blocking = (fb.blocking_issues as string[]) ?? [];
        const suggestions = (fb.suggestions as string[]) ?? [];
        return (
          <details key={r.round_number} className="rounded border border-neutral-200 dark:border-neutral-800" open={false}>
            <summary className="flex cursor-pointer items-center justify-between gap-3 px-3 py-2 text-sm">
              <span className="font-medium">Round {r.round_number}</span>
              <Bar value={r.self_satisfaction} />
            </summary>
            <div className="space-y-3 border-t border-neutral-200 p-3 dark:border-neutral-800">
              <DiffViewer diff={r.implementer_diff} />
              {(blocking.length > 0 || suggestions.length > 0) && (
                <div className="text-sm">
                  {blocking.length > 0 && (
                    <>
                      <div className="font-medium text-red-600">Blocking</div>
                      <ul className="ml-4 list-disc text-neutral-700 dark:text-neutral-300">
                        {blocking.map((b, i) => <li key={i}>{b}</li>)}
                      </ul>
                    </>
                  )}
                  {suggestions.length > 0 && (
                    <>
                      <div className="mt-1 font-medium text-amber-600">Suggestions</div>
                      <ul className="ml-4 list-disc text-neutral-700 dark:text-neutral-300">
                        {suggestions.map((s, i) => <li key={i}>{s}</li>)}
                      </ul>
                    </>
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
