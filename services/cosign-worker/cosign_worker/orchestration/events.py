"""SSE event publisher — XADD to Redis Stream stream:goal:{goal_id}.

cosign-api's SSE multiplexer consumes these and fans them out to browsers
(ARCHITECTURE §1.2). Event payloads are small; the UI fetches full transcript
detail via REST on gate open.
"""

from __future__ import annotations

import json

import structlog

log = structlog.get_logger(__name__)


class EventPublisher:
    def __init__(self, redis) -> None:
        self._redis = redis

    async def publish(self, goal_uuid: str, event: str, data: dict) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.xadd(
                f"stream:goal:{goal_uuid}",
                {"event": event, "data": json.dumps(data, default=str)},
                maxlen=5000,  # full per-goal history fits for SSE replay
                approximate=True,
            )
        except Exception as e:  # noqa: BLE001 — events are best-effort
            log.warning("sse publish failed", event=event, err=str(e))
