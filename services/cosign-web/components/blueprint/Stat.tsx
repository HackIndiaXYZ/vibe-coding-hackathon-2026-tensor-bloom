// A monospace numeric readout: small label over a value.
export function Stat({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="label">{label}</span>
      <span className={`mono text-sm ${accent ? "text-[var(--cyan)]" : "text-[var(--text)]"}`}>
        {value}
      </span>
    </div>
  );
}

// A thin progress meter (0..1) — used for self-satisfaction scores.
export function Meter({ value, width = 120 }: { value: number; width?: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="flex items-center gap-2">
      <div
        className="relative h-[6px] border border-[var(--line)] bg-[var(--ink-2)]"
        style={{ width }}
      >
        <div
          className="absolute inset-y-0 left-0 bg-[var(--cyan)]"
          style={{ width: `${pct}%`, boxShadow: "0 0 10px rgba(52,226,226,0.5)" }}
        />
      </div>
      <span className="mono text-xs tabular-nums text-[var(--text-dim)]">{value.toFixed(2)}</span>
    </div>
  );
}
