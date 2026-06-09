"""BaseTool: capability check + optional Redis cache + audit emit (ARCHITECTURE §9.2, §5.3).

Every tool goes through this so the security + cost properties hold uniformly.
Capability/audit are no-ops when no IdentityClient is wired (keeps pure tools
unit-testable without gRPC).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import structlog

from .identity_client import IdentityClient

log = structlog.get_logger(__name__)


@dataclass
class ToolContext:
    identity: IdentityClient | None = None
    redis: Any = None
    sandbox: Any = None  # SandboxDriver
    # current actor for capability + audit
    agent_id: int = 0
    goal_uuid: str = ""


# per-tool cache TTLs (seconds); 0 = never cache (ARCHITECTURE §5.3)
_TTL = {
    "github_ops": 300,
    "file_ops": 600,
    "web_search": 3600,
    "repo_map": 600,
}


class CapabilityError(PermissionError):
    pass


class BaseTool:
    name: str = "tool"
    cacheable: bool = False

    def __init__(self, ctx: ToolContext) -> None:
        self.ctx = ctx

    async def _guard(self) -> None:
        if self.ctx.identity and self.ctx.agent_id:
            ok = await self.ctx.identity.verify_capability(self.ctx.agent_id, self.name)
            if not ok:
                raise CapabilityError(f"agent {self.ctx.agent_id} not permitted to call {self.name}")

    async def _audit(self, event: str, payload: dict) -> None:
        if self.ctx.identity and self.ctx.agent_id:
            try:
                await self.ctx.identity.emit_audit_log(
                    actor_type="agent",
                    actor_id=self.ctx.agent_id,
                    event_type=event,
                    goal_uuid=self.ctx.goal_uuid,
                    payload=payload,
                )
            except Exception as e:  # noqa: BLE001 — audit must not break tool calls
                log.warning("audit emit failed", tool=self.name, err=str(e))

    def _cache_key(self, args: dict) -> str:
        raw = json.dumps(args, sort_keys=True, default=str)
        return f"tool:{self.name}:{hashlib.sha256(raw.encode()).hexdigest()}"

    async def _cache_get(self, key: str) -> Any | None:
        if not self.cacheable or self.ctx.redis is None:
            return None
        try:
            blob = await self.ctx.redis.get(key)
            return json.loads(blob) if blob else None
        except Exception:  # noqa: BLE001
            return None

    async def _cache_put(self, key: str, value: Any) -> None:
        if not self.cacheable or self.ctx.redis is None:
            return
        try:
            await self.ctx.redis.set(key, json.dumps(value, default=str), ex=_TTL.get(self.name, 300))
        except Exception:  # noqa: BLE001
            pass
