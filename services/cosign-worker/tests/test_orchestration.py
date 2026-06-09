"""End-to-end graph test with the mock router (no API keys, no GitHub).

Drives Flow B: plan -> implementer/critic loop -> loop_exit gate -> resume(approve)
-> finalize. Asserts the critic transcript persists and the gate suspends/resumes.
Skips if Postgres is unavailable.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from cosign_worker.config import Config
from cosign_worker.context import WorkerContext
from cosign_worker.llm.router import LLMRouter, load_routing_config
from cosign_worker.orchestration.events import EventPublisher
from cosign_worker.orchestration.graph import attach_orchestration

DSN = os.getenv("TEST_DATABASE_URL", "postgres://cosign:changeme@localhost:5432/cosign")


async def _pool():
    try:
        return await asyncpg.create_pool(dsn=DSN, min_size=1, max_size=4)
    except Exception:
        return None


class _FakeRedis:
    """Minimal stand-in: records XADD events, no-ops for cache."""

    def __init__(self):
        self.events = []

    async def xadd(self, key, fields, **kw):
        self.events.append((key, fields))

    async def get(self, *_):
        return None

    async def set(self, *_, **__):
        return None

    async def incr(self, *_):
        return None


@pytest.mark.asyncio
async def test_flow_b_runs_to_gate_then_finalizes():
    pool = await _pool()
    if pool is None:
        pytest.skip("no DB")
    try:
        # seed a goal
        async with pool.acquire() as c:
            user_id = await c.fetchval(
                """INSERT INTO users (github_id, github_login) VALUES ($1,$2)
                   ON CONFLICT (github_id) DO UPDATE SET github_login=EXCLUDED.github_login
                   RETURNING id""",
                770000001, "orch-test",
            )
            goal_uuid = str(uuid.uuid4())
            goal_id = await c.fetchval(
                """INSERT INTO goals (uuid, user_id, type, title, description, github_issue_number, status)
                   VALUES ($1,$2,'issue_implement','fix bug','make it work',7,'pending') RETURNING id""",
                goal_uuid, user_id,
            )

        cfg = Config.load()
        fake_redis = _FakeRedis()
        router = LLMRouter(load_routing_config("config/llm-routing.mock.yaml"), pool=pool, redis=None)
        ctx = WorkerContext(
            config=cfg, pool=pool, redis=fake_redis, router=router, sandbox=None,
            identity=None, events=EventPublisher(fake_redis),
        )
        await attach_orchestration(ctx)

        # run to the gate (no token/sandbox -> mock implementer diff, no real PR)
        config = {"configurable": {"thread_id": goal_uuid}}
        ctx.runtime[goal_uuid] = {"login": "", "token": "", "handle": None,
                                  "implementer_agent_id": 1, "reviewer_agent_id": 2}
        from cosign_worker.orchestration import dbio
        goal = await dbio.load_goal(pool, goal_uuid)
        initial = {
            "goal_id": goal.id, "goal_uuid": goal.uuid, "goal_type": goal.type,
            "user_id": goal.user_id, "repo_full_name": None, "pr_number": None,
            "issue_number": goal.issue_number, "fork_mode": False,
            "description": goal.description, "steer": "", "default_branch": "main",
            "work_branch": "cosign/issue-7", "current_round": 0, "max_iters": 5,
            "threshold": 0.85, "diff": "", "self_satisfaction": 0.0,
            "critic_feedback": {}, "misc": {},
        }
        result = await ctx.graph.ainvoke(initial, config)
        assert "__interrupt__" in result  # suspended at the gate

        # transcript persisted (mock implementer self_satisfaction 0.9 >= 0.85 -> 1 round)
        async with pool.acquire() as c:
            rounds = await c.fetch(
                "SELECT round_number, self_satisfaction FROM critic_iterations WHERE goal_id=$1 ORDER BY round_number",
                goal_id,
            )
            assert len(rounds) >= 1
            assert float(rounds[0]["self_satisfaction"]) == pytest.approx(0.9)
            gate = await c.fetchrow(
                "SELECT type FROM interrupts WHERE goal_id=$1 AND resolved_at IS NULL", goal_id
            )
            assert gate["type"] == "critic_loop_gate"
            status = await c.fetchval("SELECT status FROM goals WHERE id=$1", goal_id)
            assert status == "awaiting_human"

        # gate.pending was published
        assert any(f.get("event") == "gate.pending" for _, f in fake_redis.events)

        # resume(approve) -> finalize -> done
        from langgraph.types import Command
        await ctx.graph.ainvoke(Command(resume={"decision": "approve", "feedback": "", "edited_payload": ""}), config)
        async with pool.acquire() as c:
            status = await c.fetchval("SELECT status FROM goals WHERE id=$1", goal_id)
            assert status == "done"
            # cleanup
            await c.execute("DELETE FROM goals WHERE id=$1", goal_id)
    finally:
        await pool.close()
