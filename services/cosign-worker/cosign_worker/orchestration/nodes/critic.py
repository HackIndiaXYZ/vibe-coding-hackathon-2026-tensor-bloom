"""critic_node (Flow B) — read the diff + issue, produce structured feedback and a
score (fast/cheap model). Updates the same critic_iterations round the implementer
wrote, then loops back to the implementer.
"""

from __future__ import annotations

import structlog

from ...tools.diff_analysis import analyze_diff
from .. import dbio
from .common import build_messages, parse_json

log = structlog.get_logger(__name__)

_SYS = (
    "You are Cosign's critic. Review the implementer's diff against the issue. Return "
    "JSON: {\"blocking_issues\": [str], \"suggestions\": [str], \"score\": 0..1, "
    "\"rationale\": str}. score is your assessment of correctness+completeness. Be terse."
)


def make_critic_node(ctx):
    async def critic_node(state: dict) -> dict:
        goal_uuid = state["goal_uuid"]
        rnd = state.get("current_round", 0)
        await ctx.events.publish(goal_uuid, "task.started", {"role": "critic", "round": rnd})

        diff = state.get("diff", "")
        analysis = analyze_diff(diff) if diff else {"dangerous": False}
        task_id = await dbio.create_task(ctx.pool, state["goal_id"], "critic", None)
        user = (
            f"Issue #{state.get('issue_number')}: {state.get('description','')}\n"
            f"Dangerous patterns: {analysis.get('dangerous_reasons', [])}\n\n"
            f"DIFF:\n{diff[:16000]}"
        )
        res = await ctx.router.acall(
            role="critic", messages=build_messages(_SYS, user), task_id=task_id
        )
        feedback = parse_json(res.content, {"blocking_issues": [], "suggestions": [], "score": 0.5})

        await dbio.complete_task(ctx.pool, task_id, feedback)
        await dbio.upsert_critic_iteration(
            ctx.pool, state["goal_id"], rnd,
            critic_prompt={"system": _SYS, "user": user[:2000]},
            critic_feedback=feedback,
        )
        await ctx.events.publish(
            goal_uuid, "iteration.critic",
            {"round": rnd, "score": feedback.get("score"), "blocking": feedback.get("blocking_issues", [])},
        )
        # advance the round for the next implementer pass
        return {"critic_feedback": feedback, "current_round": rnd + 1}

    return critic_node
