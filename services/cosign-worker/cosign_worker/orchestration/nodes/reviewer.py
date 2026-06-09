"""reviewer_node (Flow A) — read the PR diff, draft a structured review, write
the pr_review_gate interrupt. cosign-api posts the (user-edited) review as the
user on resume; the worker never posts it for own-repo flows.
"""

from __future__ import annotations

import structlog

from ...tools.base import ToolContext
from ...tools.diff_analysis import analyze_diff
from ...tools.github import GithubTool
from ...tools.review import compose_review
from .. import dbio
from .common import build_messages, parse_json

log = structlog.get_logger(__name__)

_SYS = (
    "You are Cosign's reviewer, drafting a review IN THE USER'S VOICE. Read the PR "
    "diff and produce JSON: {\"summary\": str, \"risk_score\": 0..1, "
    "\"per_file_comments\": [{\"path\":str,\"line\":int,\"comment\":str}], "
    "\"ask_changes\": [str], \"praise\": [str]}. Be concrete and constructive. "
    "Never invent file paths that aren't in the diff."
)


def make_reviewer_node(ctx):
    async def reviewer_node(state: dict) -> dict:
        goal_uuid = state["goal_uuid"]
        rt = ctx.runtime.get(goal_uuid, {})
        await ctx.events.publish(goal_uuid, "task.started", {"role": "reviewer"})
        await ctx.events.publish(goal_uuid, "node.started", {"role": "reviewer"})
        await dbio.update_goal_status(ctx.pool, goal_uuid, "executing")

        owner, repo = (state["repo_full_name"].split("/", 1) + [""])[:2] \
            if state.get("repo_full_name") else ("", "")
        number = state.get("pr_number")

        diff = ""
        if rt.get("token") and owner and repo and number:
            tctx = ToolContext(
                identity=ctx.identity, redis=ctx.redis, events=ctx.events,
                agent_id=rt.get("reviewer_agent_id", 0), goal_uuid=goal_uuid,
            )
            gh = GithubTool(tctx, rt["token"])
            try:
                diff = await gh.get_pr_diff(owner, repo, number)
            except Exception as e:  # noqa: BLE001
                log.warning("get_pr_diff failed", err=str(e))

        analysis = analyze_diff(diff) if diff else {"dangerous": False, "files": []}

        task_id = await dbio.create_task(ctx.pool, state["goal_id"], "reviewer", "review")
        user = (
            f"PR #{number} on {state.get('repo_full_name')}.\n"
            f"Dangerous patterns: {analysis.get('dangerous_reasons', [])}\n\n"
            f"DIFF:\n{diff[:20000]}"
        )
        res = await ctx.router.acall(
            role="reviewer", messages=build_messages(_SYS, user), task_id=task_id,
            overrides=rt.get("routing"), key_overrides=rt.get("provider_keys"),
        )
        draft = compose_review(parse_json(res.content, {"summary": res.content}))
        await dbio.complete_task(ctx.pool, task_id, draft)
        await ctx.events.publish(
            goal_uuid, "node.completed",
            {"role": "reviewer",
             "summary": f"risk {draft['risk_score']:.2f} · {len(draft['per_file_comments'])} comments"},
        )

        # write the gate (artifact-producing node runs once; safe before interrupt)
        await dbio.create_interrupt(ctx.pool, state["goal_id"], "pr_review_gate", draft)
        await dbio.update_goal_status(ctx.pool, goal_uuid, "awaiting_human")
        await ctx.events.publish(goal_uuid, "gate.pending", {"type": "pr_review_gate"})

        return {"review_draft": draft, "misc": {"gate_payload": draft, "gate_type": "pr_review_gate"}}

    return reviewer_node
