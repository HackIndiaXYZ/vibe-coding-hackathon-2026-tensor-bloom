import type { GoalType } from "@/lib/types";

type Node = { key: string; label: string; loop?: boolean };

function nodesFor(type: GoalType): Node[] {
  if (type === "pr_review") {
    return [
      { key: "goal", label: "goal" },
      { key: "plan", label: "plan" },
      { key: "work", label: "review" },
      { key: "gate", label: "gate" },
      { key: "ship", label: "post" },
    ];
  }
  return [
    { key: "goal", label: "goal" },
    { key: "plan", label: "plan" },
    { key: "work", label: "impl ⇄ critic", loop: true },
    { key: "gate", label: "gate" },
    { key: "ship", label: "ship" },
  ];
}

function activeKey(status: string): string {
  switch (status) {
    case "pending":
    case "planning":
      return "plan";
    case "executing":
      return "work";
    case "awaiting_human":
      return "gate";
    case "done":
      return "ship";
    default:
      return "goal";
  }
}

// The goal pipeline drawn as an engineering schematic. The live node glows.
export function PipelineDiagram({
  type,
  status,
  round,
  score,
}: {
  type: GoalType;
  status: string;
  round?: number;
  score?: number;
}) {
  const nodes = nodesFor(type);
  const active = activeKey(status);
  const activeIdx = nodes.findIndex((n) => n.key === active);
  const failed = status === "failed" || status === "cancelled";

  return (
    <div className="panel ticks overflow-hidden">
      <span className="tick-bl" />
      <span className="tick-br" />
      <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-2">
        <span className="label kicker">pipeline</span>
        <span className="label">{type === "pr_review" ? "flow·a — review" : "flow·b — resolve"}</span>
      </div>

      <div className="flex items-stretch gap-0 overflow-x-auto px-4 py-6">
        {nodes.map((n, i) => {
          const done = i < activeIdx;
          const isActive = i === activeIdx && !failed;
          return (
            <div key={n.key} className="flex flex-1 items-center" style={{ minWidth: 96 }}>
              <div className="flex flex-col items-center gap-2">
                <div
                  className={[
                    "relative flex h-12 w-full min-w-[84px] items-center justify-center border px-2 mono text-xs",
                    isActive
                      ? "border-[var(--cyan)] text-[var(--cyan)]"
                      : done
                        ? "border-[var(--cyan-dim)] text-[var(--text)]"
                        : "border-[var(--line)] text-[var(--text-faint)]",
                  ].join(" ")}
                  style={isActive ? { boxShadow: "0 0 22px rgba(52,226,226,0.25)", background: "var(--cyan-deep)" } : undefined}
                >
                  {n.loop && <span className={isActive ? "pulse" : ""}>⟳ </span>}
                  {n.label}
                  {done && <span className="absolute -top-2 -right-2 text-[var(--ok)]">✓</span>}
                </div>
                <div className="h-4 label">
                  {n.key === "work" && round != null && status === "executing" && (
                    <span className="text-[var(--cyan)]">r{round}</span>
                  )}
                  {n.key === "work" && score != null && (
                    <span className="text-[var(--text-dim)]"> {score.toFixed(2)}</span>
                  )}
                </div>
              </div>
              {i < nodes.length - 1 && (
                <div
                  className="mx-1 h-px flex-1"
                  style={{
                    minWidth: 16,
                    background: i < activeIdx ? "var(--cyan-dim)" : "var(--line)",
                  }}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
