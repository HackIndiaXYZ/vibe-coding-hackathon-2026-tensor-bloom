"""Postgres I/O for orchestration (asyncpg). The worker writes only tasks,
messages, critic_iterations, interrupts, and updates goals.status (ARCHITECTURE §4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class GoalRow:
    id: int
    uuid: str
    user_id: int
    type: str
    repo_full_name: str | None
    pr_number: int | None
    issue_number: int | None
    fork_mode: bool
    description: str | None


async def load_goal(pool, goal_uuid: str) -> GoalRow | None:
    row = await pool.fetchrow(
        """
        SELECT g.id, g.uuid, g.user_id, g.type,
               COALESCE(g.repo_full_name, r.full_name) AS repo_full_name,
               g.github_pr_number, g.github_issue_number, g.fork_mode, g.description
        FROM goals g
        LEFT JOIN repositories r ON g.repository_id = r.id
        WHERE g.uuid = $1
        """,
        goal_uuid,
    )
    if row is None:
        return None
    return GoalRow(
        id=row["id"], uuid=str(row["uuid"]), user_id=row["user_id"], type=row["type"],
        repo_full_name=row["repo_full_name"], pr_number=row["github_pr_number"],
        issue_number=row["github_issue_number"], fork_mode=row["fork_mode"],
        description=row["description"],
    )


async def create_task(pool, goal_id: int, agent_role: str, tool_name: str | None = None) -> int:
    return await pool.fetchval(
        """INSERT INTO tasks (goal_id, agent_role, tool_name, status, started_at)
           VALUES ($1, $2, $3, 'running', NOW()) RETURNING id""",
        goal_id, agent_role, tool_name,
    )


async def complete_task(pool, task_id: int, result: dict) -> None:
    await pool.execute(
        "UPDATE tasks SET status='done', result_json=$2, completed_at=NOW() WHERE id=$1",
        task_id, json.dumps(result, default=str),
    )


async def update_goal_status(pool, goal_uuid: str, status: str) -> None:
    await pool.execute(
        """UPDATE goals SET status=$2, updated_at=NOW(),
               completed_at=CASE WHEN $2 IN ('done','failed','cancelled') THEN NOW() ELSE completed_at END
           WHERE uuid=$1""",
        goal_uuid, status,
    )


async def upsert_critic_iteration(
    pool, goal_id: int, round_number: int, *, implementer_prompt: dict | None = None,
    implementer_diff: str | None = None, self_satisfaction: float | None = None,
    critic_prompt: dict | None = None, critic_feedback: dict | None = None,
) -> None:
    await pool.execute(
        """
        INSERT INTO critic_iterations
            (goal_id, round_number, implementer_prompt, implementer_diff, self_satisfaction,
             critic_prompt, critic_feedback, completed_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7, NOW())
        ON CONFLICT (goal_id, round_number) DO UPDATE SET
            implementer_diff = COALESCE(EXCLUDED.implementer_diff, critic_iterations.implementer_diff),
            self_satisfaction = COALESCE(EXCLUDED.self_satisfaction, critic_iterations.self_satisfaction),
            critic_prompt = COALESCE(EXCLUDED.critic_prompt, critic_iterations.critic_prompt),
            critic_feedback = COALESCE(EXCLUDED.critic_feedback, critic_iterations.critic_feedback),
            completed_at = NOW()
        """,
        goal_id, round_number,
        json.dumps(implementer_prompt or {}), implementer_diff,
        self_satisfaction,
        json.dumps(critic_prompt) if critic_prompt is not None else None,
        json.dumps(critic_feedback) if critic_feedback is not None else None,
    )


async def create_interrupt(pool, goal_id: int, type_: str, payload: dict) -> str:
    return str(await pool.fetchval(
        """INSERT INTO interrupts (goal_id, type, payload_json) VALUES ($1,$2,$3) RETURNING uuid""",
        goal_id, type_, json.dumps(payload, default=str),
    ))
