"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/useSSE";
import type { GoalDetail, Interrupt, ResumeRequest } from "@/lib/types";
import { CostBar } from "@/components/CostBar";
import { ActivityStream } from "@/components/ActivityStream";
import { Revisions } from "@/components/Revisions";
import { CosignGate } from "@/components/CosignGate";
import { PipelineDiagram } from "@/components/blueprint/PipelineDiagram";
import { SignatureStamp } from "@/components/blueprint/SignatureStamp";
import { Tabs } from "@/components/blueprint/Tabs";
import { MockBanner } from "@/components/blueprint/Banner";

export default function GoalPage() {
  const { uuid } = useParams<{ uuid: string }>();
  const [goal, setGoal] = useState<GoalDetail | null>(null);
  const { events, connected } = useSSE(uuid);

  const refresh = useCallback(() => {
    api.getGoal(uuid).then(setGoal).catch(console.error);
  }, [uuid]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const last = events[events.length - 1];
    if (!last) return;
    if (["gate.pending", "goal.completed", "goal.failed", "goal.cancelled"].includes(last.event)) {
      refresh();
    }
  }, [events, refresh]);

  const [tab, setTab] = useState<"activity" | "revisions">("activity");
  const run = useMemo(() => events.find((e) => e.event === "run.started")?.data, [events]);
  const mock = Boolean(run?.mock);

  if (!goal) {
    return <div className="panel ticks h-40 pulse" />;
  }

  const interrupts = goal.interrupts ?? [];
  const transcript = goal.transcript ?? [];
  const costBreakdown = goal.cost_breakdown ?? [];
  const pending: Interrupt | undefined = interrupts.find((i) => !i.resolved_at);
  const lastRound = transcript[transcript.length - 1];

  async function resolve(req: ResumeRequest) {
    await api.resume(uuid, req);
    refresh();
  }

  return (
    <div className="space-y-5">
      <div className="rise flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="label kicker mb-1">{"// goal · "}{uuid.slice(0, 8)}</div>
          <h1 className="text-xl">{goal.title}</h1>
        </div>
        <div className="flex items-center gap-3">
          {goal.fork_mode && (
            <span className="label border border-[var(--line)] px-2 py-1" style={{ color: "var(--warn)" }}>
              fork-mode
            </span>
          )}
          <span className="mono text-xs" style={{ color: connected ? "var(--ok)" : "var(--text-dim)" }}>
            {connected ? "● live" : "○ offline"}
          </span>
          {goal.status === "done" && <SignatureStamp signed />}
        </div>
      </div>

      <div className="rise" style={{ animationDelay: "60ms" }}>
        <PipelineDiagram
          type={goal.type}
          status={goal.status}
          round={lastRound?.round_number}
          score={lastRound?.self_satisfaction}
        />
      </div>

      <div className="rise" style={{ animationDelay: "120ms" }}>
        <CostBar rows={costBreakdown} />
      </div>

      {pending ? (
        <CosignGate interrupt={pending} transcript={transcript} onResolve={resolve} mock={mock} />
      ) : goal.status === "done" ? (
        <div
          className="panel ticks flex items-center justify-between p-4"
          style={{ borderColor: "var(--ok)" }}
        >
          <span className="tick-bl" /><span className="tick-br" />
          <span className="text-sm" style={{ color: "var(--ok)" }}>✓ goal complete — cosigned by you.</span>
          {goal.output_url && (
            <a href={goal.output_url} target="_blank" rel="noreferrer" className="btn">
              view on github →
            </a>
          )}
        </div>
      ) : null}

      {mock && (
        <div className="rise" style={{ animationDelay: "150ms" }}>
          <MockBanner model={run?.model as string | undefined} />
        </div>
      )}

      <div className="rise" style={{ animationDelay: "180ms" }}>
        <div className="mb-2 flex items-center justify-between">
          <Tabs
            tabs={[
              { key: "activity", label: "activity", badge: events.length || undefined },
              { key: "revisions", label: "revisions", badge: transcript.length || undefined },
            ]}
            active={tab}
            onChange={(k) => setTab(k as "activity" | "revisions")}
          />
          <span className="label">{connected ? "● streaming" : "○ idle"}</span>
        </div>
        <div className="panel ticks">
          <span className="tick-bl" /><span className="tick-br" />
          <div className="max-h-[28rem] overflow-y-auto p-4">
            {tab === "activity" ? (
              <ActivityStream events={events} />
            ) : (
              <Revisions rounds={transcript} mock={mock} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
