import type { ReactNode } from "react";

// A schematic blueprint panel: 1px frame + cyan corner ticks + optional title tab.
export function Panel({
  title,
  right,
  children,
  className = "",
}: {
  title?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`panel ticks ${className}`}>
      <span className="tick-bl" />
      <span className="tick-br" />
      {(title || right) && (
        <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-2">
          {title && <span className="label kicker">{title}</span>}
          {right && <div className="label">{right}</div>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}
