"use client";

import { useEffect, useRef, useState } from "react";
import { streamUrl } from "./api";
import type { SSEEvent } from "./types";

// useSSE subscribes to a goal's event stream. EventSource auto-reconnects and
// replays via Last-Event-ID; it sends cookies (withCredentials).
export function useSSE(goalUuid: string | null) {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!goalUuid) return;
    const es = new EventSource(streamUrl(goalUuid), { withCredentials: true });
    esRef.current = es;
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    const types = [
      "task.started", "task.tool_call", "task.completed", "task.failed",
      "iteration.implementer", "iteration.critic", "gate.pending", "gate.resolved",
      "goal.completed", "goal.failed", "goal.cancelled", "goal.status_changed", "message",
    ];
    const handler = (e: MessageEvent) => {
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(e.data);
      } catch {
        /* ignore non-JSON */
      }
      setEvents((prev) => [...prev, { id: e.lastEventId, event: e.type, data }]);
    };
    for (const t of types) es.addEventListener(t, handler as EventListener);

    return () => {
      for (const t of types) es.removeEventListener(t, handler as EventListener);
      es.close();
    };
  }, [goalUuid]);

  return { events, connected };
}
