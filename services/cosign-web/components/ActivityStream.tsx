"use client";

import { useEffect, useMemo, useRef } from "react";
import type { SSEEvent } from "@/lib/types";

type ToolRow = {
  tool: string;
  label: string;
  detail?: string;
  status: "running" | "ok" | "error";
  summary?: string;
  ms?: number;
};
type Stage = {
  key: string;
  role: string;
  round?: number;
  label: string;
  status: "running" | "done";
  summary: string;
  score?: number;
  tools: ToolRow[];
};
type Marker = { event: string; data: Record<string, unknown> };

function stageLabel(role: string, round?: number): string {
  if (role === "plan") return "plan";
  if (role === "implementer") return `implement · r${round ?? 0}`;
  if (role === "critic") return `critic · r${round ?? 0}`;
  if (role === "reviewer") return "review";
  return role;
}

function build(events: SSEEvent[]): { stages: Stage[]; markers: Marker[] } {
  const stages: Stage[] = [];
  const markers: Marker[] = [];
  let cur: Stage | null = null;

  for (const e of events) {
    const d = (e.data ?? {}) as Record<string, unknown>;
    if (e.event === "run.started") continue;
    const role = d.role as string | undefined;

    if (role) {
      const round = d.round as number | undefined;
      const key = `${role}:${round ?? ""}`;
      if (!cur || cur.key !== key) {
        cur = { key, role, round, label: stageLabel(role, round), status: "running", summary: "", tools: [] };
        stages.push(cur);
      }
      if (e.event === "node.completed") {
        cur.status = "done";
        cur.summary = (d.summary as string) || cur.summary;
      } else if (e.event === "iteration.implementer") {
        cur.score = d.self_satisfaction as number;
        cur.summary = (d.summary as string) || cur.summary;
      } else if (e.event === "iteration.critic") {
        cur.score = d.score as number;
      }
      continue;
    }

    if (e.event === "task.tool_call" && cur) {
      cur.tools.push({
        tool: d.tool as string, label: d.label as string,
        detail: d.detail as string, status: "running",
      });
    } else if (e.event === "task.tool_result" && cur) {
      for (let i = cur.tools.length - 1; i >= 0; i--) {
        const t = cur.tools[i];
        if (t.tool === d.tool && t.label === d.label && t.status === "running") {
          t.status = (d.status as "ok" | "error") ?? "ok";
          t.summary = d.summary as string;
          t.ms = d.duration_ms as number;
          break;
        }
      }
    } else if (["gate.pending", "goal.completed", "goal.failed", "goal.cancelled"].includes(e.event)) {
      markers.push({ event: e.event, data: d });
    }
  }
  return { stages, markers };
}

const TOOL_ICON: Record<string, string> = {
  repo_map: "▤", file_ops: "✎", code_exec: "⌘", test_runner: "✓", lint: "≣",
  github_ops: "⎇", diff_analysis: "◫", review: "❝",
};

export function ActivityStream({ events }: { events: SSEEvent[] }) {
  const { stages, markers } = useMemo(() => build(events), [events]);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length]);

  if (stages.length === 0) {
    return <div className="mono text-xs text-[var(--text-dim)] pulse">awaiting trace…</div>;
  }

  return (
    <div className="space-y-2">
      {stages.map((s, i) => {
        const live = s.status === "running" && i === stages.length - 1;
        return (
          <div key={`${s.key}-${i}`} className="border border-[var(--line)]">
            <div className="flex items-center gap-2 border-b border-[var(--line)] px-3 py-2">
              <span
                className={`mono text-sm ${live ? "pulse" : ""}`}
                style={{ color: live ? "var(--cyan)" : "var(--text)" }}
              >
                {live ? "⟳" : "✓"}
              </span>
              <span className="mono text-sm text-[var(--text)]">{s.label}</span>
              {s.score != null && (
                <span className="mono text-xs text-[var(--text-dim)]">· score {s.score.toFixed(2)}</span>
              )}
              {s.summary && <span className="ml-auto truncate text-xs text-[var(--text-dim)]">{s.summary}</span>}
            </div>
            {s.tools.length > 0 && (
              <ul className="px-3 py-2">
                {s.tools.map((t, j) => (
                  <li key={j} className="flex items-center gap-2 mono text-xs">
                    <span className="text-[var(--text-faint)]">└</span>
                    <span className="w-4 text-center text-[var(--cyan)]">{TOOL_ICON[t.tool] ?? "·"}</span>
                    <span className="text-[var(--text)]">{t.tool}</span>
                    <span className="text-[var(--text-dim)]">{t.label}{t.detail ? ` ${t.detail}` : ""}</span>
                    <span className="ml-auto flex items-center gap-2">
                      {t.summary && <span className="text-[var(--text-dim)]">{t.summary}</span>}
                      {t.ms != null && <span className="text-[var(--text-faint)]">{t.ms}ms</span>}
                      <span style={{ color: t.status === "ok" ? "var(--ok)" : t.status === "error" ? "var(--danger)" : "var(--cyan)" }}>
                        {t.status === "running" ? "⟳" : t.status === "ok" ? "✓" : "✗"}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}

      {markers.map((m, i) => (
        <div key={i} className="flex items-center gap-2 px-1 py-1 mono text-xs">
          <span style={{ color: m.event === "gate.pending" ? "var(--warn)" : m.event === "goal.completed" ? "var(--ok)" : "var(--danger)" }}>
            {m.event === "gate.pending" ? "✋ gate ready — awaiting your cosign" :
              m.event === "goal.completed" ? "◆ goal complete" :
              m.event === "goal.failed" ? `✗ failed: ${m.data.error ?? ""}` : "⊘ cancelled"}
          </span>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
