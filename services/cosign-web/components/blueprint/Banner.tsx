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
