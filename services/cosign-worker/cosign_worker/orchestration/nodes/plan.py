"""plan_node — decompose the goal into a small step list (cheap model)."""

from __future__ import annotations

import structlog

from .. import dbio
from .common import build_messages, parse_json

log = structlog.get_logger(__name__)

_SYS = (
    "You are Cosign's planner. Given a goal (review a PR, or implement an issue), "
    "produce a short JSON plan: {\"steps\": [\"...\", \"...\"]}. Keep it under 5 steps."
)


def make_plan_node(ctx):
    async def plan_node(state: dict) -> dict:
        goal_uuid = state["goal_uuid"]
        await ctx.events.publish(goal_uuid, "task.started", {"role": "plan"})
        await dbio.update_goal_status(ctx.pool, goal_uuid, "planning")

        task_id = await dbio.create_task(ctx.pool, state["goal_id"], "plan", None)
        user = (
            f"Goal type: {state['goal_type']}\n"
            f"Repo: {state.get('repo_full_name')}\n"
            f"Target: PR #{state.get('pr_number')} / Issue #{state.get('issue_number')}\n"
            f"Notes: {state.get('steer','')}"
        )
        try:
            res = await ctx.router.acall(
                role="plan_node", messages=build_messages(_SYS, user), task_id=task_id
            )
            plan = parse_json(res.content, {}).get("steps", [])
        except Exception as e:  # noqa: BLE001 — planning is non-critical
            log.warning("plan failed", err=str(e))
            plan = []
        await dbio.complete_task(ctx.pool, task_id, {"steps": plan})
        return {"plan": plan}

    return plan_node
