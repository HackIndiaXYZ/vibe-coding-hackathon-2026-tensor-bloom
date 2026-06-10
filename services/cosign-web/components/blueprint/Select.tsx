"use client";

import { useEffect, useRef, useState } from "react";

export type Option = { value: string; label?: string };

// A standard Engineered-Blueprint dropdown — replaces native <select> so the
// option list matches the dark theme. Keyboard + outside-click + escape aware.
export function Select({
  value,
  options,
  placeholder = "select",
  disabled = false,
  onChange,
  className = "",
}: {
  value: string;
  options: Option[];
  placeholder?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value);

  function openMenu() {
    const i = options.findIndex((o) => o.value === value);
    setActive(i >= 0 ? i : 0);
    setOpen(true);
  }

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function pick(v: string) {
    onChange(v);
    setOpen(false);
  }

  function onKey(e: React.KeyboardEvent) {
    if (disabled) return;
    if (!open) {
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
        e.preventDefault();
        openMenu();
      }
      return;
    }
    if (e.key === "Escape") setOpen(false);
    else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, options.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const o = options[active];
      if (o) pick(o.value);
    }
  }

  return (
    <div ref={ref} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (disabled ? null : open ? setOpen(false) : openMenu())}
        onKeyDown={onKey}
        className="field flex w-full items-center justify-between gap-2 text-left disabled:opacity-40"
      >
        <span className={selected ? "text-[var(--text)]" : "text-[var(--text-faint)]"}>
          {selected?.label ?? selected?.value ?? placeholder}
        </span>
        <span className="text-[var(--cyan)]" style={{ transition: "transform 0.15s", transform: open ? "rotate(180deg)" : "none" }}>
          ▾
        </span>
      </button>

      {open && (
        <ul
          role="listbox"
          className="bp-pop ticks max-h-64 w-full overflow-y-auto"
          style={{
            // inline position beats the `.panel` class (which forces relative)
            position: "absolute",
            top: "100%",
            left: 0,
            marginTop: 4,
            zIndex: 40,
            background: "var(--panel)",
            border: "1px solid var(--line)",
            boxShadow: "0 12px 40px rgba(0,0,0,0.6)",
          }}
        >
          <span className="tick-bl" /><span className="tick-br" />
          {options.map((o, i) => {
            const on = o.value === value;
            const hot = i === active;
            return (
              <li
                key={o.value || `opt-${i}`}
                role="option"
                aria-selected={on}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => { e.preventDefault(); pick(o.value); }}
                className="flex cursor-pointer items-center gap-2 px-3 py-1.5 mono text-xs"
                style={{
                  background: hot ? "var(--cyan-deep)" : "transparent",
                  color: on ? "var(--cyan)" : "var(--text)",
                }}
              >
                <span className="w-3 text-[var(--cyan)]">{on ? "▸" : ""}</span>
                {o.label ?? (o.value || placeholder)}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
