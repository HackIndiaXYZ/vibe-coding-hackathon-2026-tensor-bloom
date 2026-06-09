"""finalize_node — act on the human decision (ARCHITECTURE §3).

Flow A (pr_review): cosign-api already posted the review as the user on resume;
the worker just marks the goal done.
Flow B (issue_implement): on approve, push the branch + open the PR as the user
(via their OAuth token). reject -> cancelled.
"""

from __future__ import annotations

import structlog

from ...tools.base import ToolContext
from ...tools.github import GithubTool
from .. import dbio

log = structlog.get_logger(__name__)


def make_finalize_node(ctx):
    async def finalize_node(state: dict) -> dict:
        goal_uuid = state["goal_uuid"]
        decision = state.get("decision", "approve")
        rt = ctx.runtime.get(goal_uuid, {})

        if decision == "reject":
            await dbio.update_goal_status(ctx.pool, goal_uuid, "cancelled")
            await ctx.events.publish(goal_uuid, "goal.cancelled", {})
            return {"output_url": ""}

        output_url = ""
        if state["goal_type"] == "issue_implement" and decision == "approve":
            output_url = await _open_pr(ctx, state, rt)

        await dbio.update_goal_status(ctx.pool, goal_uuid, "done")
        await ctx.events.publish(goal_uuid, "goal.completed", {"output_url": output_url})
        return {"output_url": output_url}

    return finalize_node


async def _open_pr(ctx, state: dict, rt: dict) -> str:
    handle = rt.get("handle")
    token = rt.get("token")
    repo_full = state.get("repo_full_name") or ""
    if not (handle and token and "/" in repo_full):
        log.info("finalize: no real repo/token; skipping push+PR (mock/dev run)")
        return ""
    owner, repo = repo_full.split("/", 1)
    branch = state.get("work_branch") or f"cosign/issue-{state.get('issue_number')}"
    base = state.get("default_branch") or "main"
    try:
        await ctx.sandbox.commit_and_push(
            handle, branch, f"Cosign: resolve issue #{state.get('issue_number')}"
        )
        await ctx.sandbox.push(handle, branch, token)
        tctx = ToolContext(
            identity=ctx.identity, redis=ctx.redis,
            agent_id=rt.get("implementer_agent_id", 0), goal_uuid=state["goal_uuid"],
        )
        gh = GithubTool(tctx, token)
        head = f"{rt['login']}:{branch}" if state.get("fork_mode") else branch
        res = await gh.open_pr(
            owner, repo,
            title=f"Resolve #{state.get('issue_number')} (via Cosign)",
            head=head, base=base,
            body=f"Resolves #{state.get('issue_number')}.\n\nAuthored by @{rt.get('login')} via Cosign.",
        )
        return res.get("url", "")
    except Exception as e:  # noqa: BLE001
        log.error("finalize push/PR failed", err=str(e))
        await ctx.events.publish(state["goal_uuid"], "goal.failed", {"error": str(e)})
        return ""
