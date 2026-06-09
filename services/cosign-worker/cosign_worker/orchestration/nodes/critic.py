"""critic_node (Flow B) — read the diff + issue, produce structured feedback and a
score (fast/cheap model). Updates the same critic_iterations round the implementer
wrote, then loops back to the implementer.
"""

from __future__ import annotations

import structlog

from .. import dbio
from .common import build_messages, parse_json

log = structlog.get_logger(__name__)

_SYS = (
    "You are Cosign's critic. Review the implementer's diff against the issue. Return "
    "JSON: {\"blocking_issues\": [str], \"suggestions\": [str], \"score\": 0..1, "
    "\"rationale\": str}. score is your assessment of correctness+completeness. Be terse."
)

# Round-varying mock feedback so the loop iterates believably for keyless demos.
_MOCK_CRITIC = [
    {"blocking_issues": ["no error handling for missing input"],
     "suggestions": ["guard the IO call", "return None on failure"],
     "score": 0.62, "rationale": "happy-path only"},
    {"blocking_issues": [],
     "suggestions": ["add a regression test"],
     "score": 0.79, "rationale": "logic ok, needs coverage"},
    {"blocking_issues": [], "suggestions": [],
     "score": 0.93, "rationale": "correct and covered"},
]


def make_critic_node(ctx):
    async def critic_node(state: dict) -> dict:
        goal_uuid = state["goal_uuid"]
        rt = ctx.runtime.get(goal_uuid, {})
        rnd = state.get("current_round", 0)
        await ctx.events.publish(goal_uuid, "task.started", {"role": "critic", "round": rnd})
        await ctx.events.publish(goal_uuid, "node.started", {"role": "critic", "round": rnd})

        diff = state.get("diff", "")
        # diff_analysis as a tracked tool call (drives the dangerous-action gate)
        from ...tools.base import ToolContext
        from ...tools.diff_analysis import DiffAnalysisTool

        dtctx = ToolContext(
            identity=ctx.identity, redis=ctx.redis, events=ctx.events,
            agent_id=rt.get("critic_agent_id", 3), goal_uuid=goal_uuid,
        )
        analysis = await DiffAnalysisTool(dtctx).run(diff) if diff else {"dangerous": False}
        task_id = await dbio.create_task(ctx.pool, state["goal_id"], "critic", None)
        user = (
            f"Issue #{state.get('issue_number')}: {rt.get('issue_title') or state.get('description','')}\n"
            f"{(rt.get('issue_body') or '')[:2000]}\n"
            f"Dangerous patterns: {analysis.get('dangerous_reasons', [])}\n\n"
            f"DIFF:\n{diff[:16000]}"
        )
        try:
            res = await ctx.router.acall(
                role="critic", messages=build_messages(_SYS, user), task_id=task_id,
                overrides=rt.get("routing"), key_overrides=rt.get("provider_keys"),
            )
            feedback = parse_json(res.content, {"blocking_issues": [], "suggestions": [], "score": 0.5})
            if res.provider == "mock":
                feedback = _MOCK_CRITIC[min(rnd, len(_MOCK_CRITIC) - 1)]
        except Exception as e:  # noqa: BLE001 — critic is advisory; never fail the goal
            log.warning("critic llm failed; degrading", err=str(e))
            await ctx.events.publish(goal_uuid, "task.tool_result", {
                "tool": "critic", "label": "review", "status": "error",
                "summary": "model unavailable — skipped this round",
            })
            # neutral feedback nudges the loop forward toward the gate
            feedback = {"blocking_issues": [], "suggestions": ["critic skipped (model unavailable)"],
                        "score": min(0.85, (state.get("self_satisfaction") or 0.5) + 0.1),
                        "rationale": "critic unavailable"}

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
        await ctx.events.publish(
            goal_uuid, "node.completed",
            {"role": "critic", "round": rnd,
             "summary": f"score {feedback.get('score')} · {len(feedback.get('blocking_issues', []))} blocking"},
        )
        # advance the round for the next implementer pass
        return {"critic_feedback": feedback, "current_round": rnd + 1}

    return critic_node
