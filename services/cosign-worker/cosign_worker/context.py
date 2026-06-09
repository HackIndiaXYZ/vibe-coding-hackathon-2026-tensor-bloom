"""Shared worker context: the long-lived dependencies nodes + RPCs use.

The `runtime` dict holds per-goal, in-memory, NON-checkpointed state (the user's
OAuth token + live SandboxHandle) keyed by goal_uuid — these must never reach the
Postgres checkpoint store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .config import Config


@dataclass
class WorkerContext:
    config: Config
    pool: Any = None  # asyncpg.Pool
    redis: Any = None  # redis.asyncio.Redis
    router: Any = None  # LLMRouter
    sandbox: Any = None  # SandboxDriver
    identity: Any = None  # IdentityClient (gRPC to cosign-api)
    events: Any = None  # EventPublisher
    graph: Any = None  # compiled LangGraph
    checkpointer: Any = None  # AsyncPostgresSaver

    # per-goal in-memory runtime (token, sandbox handle, agent ids) — NOT checkpointed
    runtime: dict[str, dict] = field(default_factory=dict)

    # Orchestration hooks, set by attach_orchestration() in Phase 5.
    run_goal: Callable[[str], Awaitable[None]] | None = field(default=None)
    resume_goal: Callable[[str, str, str, str], Awaitable[None]] | None = field(default=None)
    cancel_goal: Callable[[str], Awaitable[None]] | None = field(default=None)
