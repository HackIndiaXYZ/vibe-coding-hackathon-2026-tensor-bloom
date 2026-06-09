"use client";

import { useEffect, useState } from "react";

export type ToastKind = "ok" | "error";
export type ToastMsg = { id: number; text: string; kind: ToastKind };

// A tiny imperative toast hook + a fixed blueprint container.
export function useToast() {
  const [toasts, setToasts] = useState<ToastMsg[]>([]);
  function push(text: string, kind: ToastKind = "ok") {
    const id = Date.now() + Math.floor(performance.now());
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 2600);
  }
  return { toasts, push };
}

export function ToastHost({ toasts }: { toasts: ToastMsg[] }) {
  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <Toast key={t.id} {...t} />
      ))}
    </div>
  );
}

function Toast({ text, kind }: ToastMsg) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const r = requestAnimationFrame(() => setShow(true));
    return () => cancelAnimationFrame(r);
  }, []);
  const color = kind === "ok" ? "var(--ok)" : "var(--danger)";
  return (
    <div
      className="panel ticks flex items-center gap-2 px-3 py-2 mono text-xs"
      style={{
        borderColor: color,
        boxShadow: `0 0 24px ${kind === "ok" ? "rgba(52,211,153,0.18)" : "rgba(248,113,113,0.18)"}`,
        transform: show ? "translateX(0)" : "translateX(12px)",
        opacity: show ? 1 : 0,
        transition: "all 0.25s cubic-bezier(0.2,0.7,0.2,1)",
      }}
    >
      <span className="tick-bl" /><span className="tick-br" />
      <span style={{ color }}>{kind === "ok" ? "✓" : "!"}</span>
      <span className="text-[var(--text)]">{text}</span>
    </div>
  );
}
