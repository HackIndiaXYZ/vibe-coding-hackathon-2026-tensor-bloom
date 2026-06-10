// Demo budget banner — shows the shared key + per-user spend, or "own key" state.
export function BudgetBanner({
  sharedKeyAvailable,
  usingOwnKey,
  usageUsd,
  capUsd,
  defaultModel,
}: {
  sharedKeyAvailable: boolean;
  usingOwnKey: boolean;
  usageUsd: number;
  capUsd: number;
  defaultModel: string;
}) {
  if (!sharedKeyAvailable) return null;

  if (usingOwnKey) {
    return (
      <div className="panel ticks flex items-center gap-3 p-3" style={{ borderColor: "var(--ok)" }}>
        <span className="tick-bl" /><span className="tick-br" />
        <span className="mono text-sm" style={{ color: "var(--ok)" }}>◆ YOUR KEY</span>
        <p className="text-xs text-[var(--text-dim)]">
          Using your own provider key — no budget cap. You&apos;re billed by your provider directly.
        </p>
      </div>
    );
  }

  const pct = Math.min(1, capUsd > 0 ? usageUsd / capUsd : 0);
  const over = usageUsd >= capUsd;
  const color = over ? "var(--warn)" : "var(--cyan)";
  return (
    <div className="panel ticks p-3" style={{ borderColor: color }}>
      <span className="tick-bl" /><span className="tick-br" />
      <div className="flex items-center gap-3">
        <span className="mono text-sm" style={{ color }}>{over ? "⚠ BUDGET REACHED" : "◆ SHARED KEY"}</span>
        <p className="text-xs text-[var(--text-dim)]">
          {over ? (
            <>Demo budget used up — <span className="text-[var(--text)]">add your own key below</span> to keep running.</>
          ) : (
            <>A shared <span className="mono text-[var(--text)]">{defaultModel.split("/").pop()}</span> key is
              provided for the demo. Add your own key below to remove the cap.</>
          )}
        </p>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div className="h-[6px] flex-1 border border-[var(--line)] bg-[var(--ink-2)]">
          <div className="h-full" style={{ width: `${pct * 100}%`, background: color }} />
        </div>
        <span className="mono text-xs tabular-nums" style={{ color }}>
          ${usageUsd.toFixed(3)} / ${capUsd.toFixed(2)}
        </span>
      </div>
    </div>
  );
}

// MOCK MODE notice — explains synthetic diffs + how to switch to real models.
export function MockBanner({ model }: { model?: string }) {
  return (
    <div
      className="panel ticks flex items-start gap-3 p-3"
      style={{ borderColor: "var(--warn)" }}
    >
      <span className="tick-bl" /><span className="tick-br" />
      <span className="mono text-sm" style={{ color: "var(--warn)" }}>⚠ MOCK MODE</span>
      <p className="text-xs text-[var(--text-dim)]">
        Running on the mock LLM{model ? ` (${model})` : ""} — diffs and scores are synthetic
        (no API keys). Code changes shown are illustrative, not real edits. To produce real diffs,
        add provider keys in <span className="mono text-[var(--text)]">/settings</span> and set
        <span className="mono text-[var(--text)]"> LLM_ROUTING_CONFIG=config/llm-routing.yaml</span>.
      </p>
    </div>
  );
}
