"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSSE } from "@/lib/useSSE";
import type { GoalDetail, Interrupt, ResumeRequest } from "@/lib/types";
import { CostBar } from "@/components/CostBar";
import { EventFeed } from "@/components/EventFeed";
import { CosignGate } from "@/components/CosignGate";

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

  // Re-fetch detail whenever a gate or terminal event arrives.
  useEffect(() => {
    const last = events[events.length - 1];
    if (!last) return;
    if (["gate.pending", "goal.completed", "goal.failed", "goal.cancelled"].includes(last.event)) {
      refresh();
    }
  }, [events, refresh]);

  if (!goal) {
    return <div className="h-40 animate-pulse rounded bg-neutral-100 dark:bg-neutral-900" />;
  }

  const pending: Interrupt | undefined = goal.interrupts.find((i) => !i.resolved_at);

  async function resolve(req: ResumeRequest) {
    await api.resume(uuid, req);
    refresh();
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">{goal.title}</h1>
        <div className="mt-1 flex items-center gap-3 text-xs text-neutral-500">
          <span>{goal.status}</span>
          <span>·</span>
          <span>{connected ? "live" : "disconnected"}</span>
          {goal.fork_mode && <span className="rounded bg-amber-100 px-1.5 text-amber-700">fork-mode</span>}
          {goal.output_url && (
            <a href={goal.output_url} className="text-blue-600 underline" target="_blank" rel="noreferrer">
              view on GitHub
            </a>
          )}
        </div>
      </div>

      <CostBar rows={goal.cost_breakdown} />

      {pending ? (
        <CosignGate interrupt={pending} transcript={goal.transcript} onResolve={resolve} />
      ) : goal.status === "done" ? (
        <div className="rounded border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
          Goal complete — cosigned by you.
        </div>
      ) : null}

      <section>
        <h2 className="mb-2 text-sm font-medium text-neutral-500">
          Live activity {connected ? "●" : "○"}
        </h2>
        <EventFeed events={events} />
      </section>
    </div>
  );
}
