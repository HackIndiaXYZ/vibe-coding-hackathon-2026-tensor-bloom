"use client";

import { useState } from "react";
import type { CriticIteration } from "@/lib/types";
import { DiffViewer } from "./DiffViewer";
import { Meter } from "./blueprint/Stat";

// Browse every revised version of the code (per-round diffs) with compare.
export function Revisions({ rounds, mock = false }: { rounds: CriticIteration[]; mock?: boolean }) {
  const [sel, setSel] = useState(0);
  const [compare, setCompare] = useState(false);

  if (rounds.length === 0) {
    return <div className="mono text-xs text-[var(--text-dim)]">no revisions yet</div>;
  }
  const idx = Math.min(sel, rounds.length - 1);
  const cur = rounds[idx];
  const prev = idx > 0 ? rounds[idx - 1] : null;
  const fb = (cur.critic_feedback ?? {}) as Record<string, unknown>;
  const blocking = (fb.blocking_issues as string[]) ?? [];
  const suggestions = (fb.suggestions as string[]) ?? [];

  return (
    <div className="space-y-3">
      {/* version rail */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="label">versions</span>
        {rounds.map((r, i) => {
          const on = i === idx;
          return (
            <button
              key={r.round_number}
              onClick={() => setSel(i)}
              className="mono border px-3 py-1.5 text-xs transition-colors"
              style={
                on
                  ? { borderColor: "var(--cyan)", color: "var(--cyan)", background: "var(--cyan-deep)" }
                  : { borderColor: "var(--line)", color: "var(--text-dim)" }
              }
            >
              R{r.round_number}
              {r.self_satisfaction != null && (
                <span className="ml-2 text-[var(--text-faint)]">{r.self_satisfaction.toFixed(2)}</span>
              )}
            </button>
          );
        })}
        {prev && (
          <button
            onClick={() => setCompare((c) => !c)}
            className="mono ml-auto border px-3 py-1.5 text-xs"
            style={compare ? { borderColor: "var(--cyan)", color: "var(--cyan)" } : { borderColor: "var(--line)", color: "var(--text-dim)" }}
          >
            {compare ? "[ compare ]" : "compare ▸ prev"}
          </button>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="mono text-sm text-[var(--cyan)]">revision R{cur.round_number}</span>
        <Meter value={cur.self_satisfaction ?? 0} />
        {mock && (
          <span className="mono text-xs" style={{ color: "var(--warn)" }}>
            synthetic (mock — not your repo)
          </span>
        )}
      </div>

      {compare && prev ? (
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <div className="label mb-1">previous · R{prev.round_number}</div>
            <DiffViewer diff={prev.implementer_diff} />
          </div>
          <div>
            <div className="label mb-1" style={{ color: "var(--cyan)" }}>this · R{cur.round_number}</div>
            <DiffViewer diff={cur.implementer_diff} />
          </div>
        </div>
      ) : (
        <DiffViewer diff={cur.implementer_diff} />
      )}

      {(blocking.length > 0 || suggestions.length > 0) && (
        <div className="border border-[var(--line)] p-3 mono text-xs">
          <div className="label mb-1">critic feedback · R{cur.round_number}</div>
          {blocking.map((b, i) => (
            <div key={`b${i}`} style={{ color: "var(--danger)" }}>✗ {b}</div>
          ))}
          {suggestions.map((s, i) => (
            <div key={`s${i}`} style={{ color: "var(--warn)" }}>→ {s}</div>
          ))}
        </div>
      )}
    </div>
  );
}
