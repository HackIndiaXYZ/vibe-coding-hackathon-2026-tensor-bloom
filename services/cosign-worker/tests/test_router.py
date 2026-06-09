"""LLMRouter tests: role resolution, provider:none, mock call, cost recording."""

from __future__ import annotations

import os

import asyncpg
import pytest

from cosign_worker.llm.router import LLMRouter, ProviderNoneError, load_routing_config

MOCK_CFG = {
    "defaults": {"provider": "mock", "model": "d"},
    "roles": {
        "implementer": {"provider": "mock", "model": "impl", "mock_response": '{"x":1}', "mock_cost_usd": 0.002},
        "plan_node": {"provider": "anthropic", "model": "claude", "api_key_env": "MISSING_KEY"},
    },
    "tools": {"repo_map": {"provider": "none"}},
}


def test_resolution_prefers_tool_then_role_then_default():
    r = LLMRouter(MOCK_CFG)
    assert r._resolve("implementer", None)["model"] == "impl"
    assert r._resolve(None, "repo_map")["provider"] == "none"
    assert r._resolve("unknown", None)["model"] == "d"


def test_is_none():
    r = LLMRouter(MOCK_CFG)
    assert r.is_none(tool="repo_map") is True
    assert r.is_none(role="implementer") is False


@pytest.mark.asyncio
async def test_provider_none_raises():
    r = LLMRouter(MOCK_CFG)
    with pytest.raises(ProviderNoneError):
        await r.acall(tool="repo_map", messages=[{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_mock_call_returns_result():
    r = LLMRouter(MOCK_CFG)
    res = await r.acall(role="implementer", messages=[{"role": "user", "content": "do it"}])
    assert res.provider == "mock"
    assert res.content == '{"x":1}'
    assert res.cost_usd == 0.002


@pytest.mark.asyncio
async def test_real_default_mock_config_loads():
    cfg = load_routing_config("config/llm-routing.mock.yaml")
    r = LLMRouter(cfg)
    res = await r.acall(role="critic", messages=[{"role": "user", "content": "review"}])
    assert res.provider == "mock"
    assert "score" in res.content


@pytest.mark.asyncio
async def test_cost_recorded_to_messages():
    dsn = os.getenv("TEST_DATABASE_URL", "postgres://cosign:changeme@localhost:5432/cosign")
    try:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    except Exception:
        pytest.skip("no DB")
    try:
        async with pool.acquire() as conn:
            # minimal goal + task to satisfy FKs
            user_id = await conn.fetchval(
                """INSERT INTO users (github_id, github_login) VALUES ($1,$2)
                   ON CONFLICT (github_id) DO UPDATE SET github_login=EXCLUDED.github_login
                   RETURNING id""",
                880000001, "router-test",
            )
            goal_id = await conn.fetchval(
                """INSERT INTO goals (user_id, type, title, status)
                   VALUES ($1,'manual','router test','executing') RETURNING id""",
                user_id,
            )
            task_id = await conn.fetchval(
                """INSERT INTO tasks (goal_id, agent_role, status)
                   VALUES ($1,'implementer','running') RETURNING id""",
                goal_id,
            )

        r = LLMRouter(MOCK_CFG, pool=pool)
        await r.acall(role="implementer", messages=[{"role": "user", "content": "x"}], task_id=task_id)

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT role, cost_usd FROM messages WHERE task_id=$1 ORDER BY id DESC LIMIT 1",
                task_id,
            )
            assert row is not None
            assert row["role"] == "assistant"
            assert float(row["cost_usd"]) == pytest.approx(0.002)
            # cleanup
            await conn.execute("DELETE FROM goals WHERE id=$1", goal_id)
    finally:
        await pool.close()
