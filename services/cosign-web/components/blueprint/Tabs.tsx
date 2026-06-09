"use client";

// A blueprint segmented control.
export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: string; label: string; badge?: string | number }[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="inline-flex border border-[var(--line)]">
      {tabs.map((t, i) => {
        const on = t.key === active;
        return (
          <button
            key={t.key}
            onClick={() => onChange(t.key)}
            className={`mono px-4 py-2 text-xs tracking-wide transition-colors ${i > 0 ? "border-l border-[var(--line)]" : ""}`}
            style={
              on
                ? { background: "var(--cyan-deep)", color: "var(--cyan)" }
                : { color: "var(--text-dim)" }
            }
          >
            {on ? `[ ${t.label} ]` : t.label}
            {t.badge != null && <span className="ml-2 text-[var(--text-faint)]">{t.badge}</span>}
          </button>
        );
      })}
    </div>
  );
}
