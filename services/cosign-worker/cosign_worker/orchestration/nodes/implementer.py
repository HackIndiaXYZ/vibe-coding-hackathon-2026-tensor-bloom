"""implementer_node (Flow B) — read issue + repo + prior critic feedback, emit a
diff and a self-satisfaction score. Applies file edits in the sandbox when a real
repo is checked out; otherwise uses the model's proposed diff (mock/keyless dev).
"""

from __future__ import annotations

import structlog

from ...tools.base import ToolContext
from ...tools.code import FileOpsTool
from .. import dbio
from .common import build_messages, parse_json

log = structlog.get_logger(__name__)

_SYS = (
    "You are Cosign's implementer. Resolve the issue by editing files. Return JSON: "
    "{\"files\": [{\"path\": str, \"content\": str}], \"summary\": str, "
    "\"self_satisfaction\": 0..1}. self_satisfaction reflects how confident you are "
    "the change is correct and complete. Address every point of prior critic feedback."
)


def make_implementer_node(ctx):
    async def implementer_node(state: dict) -> dict:
        goal_uuid = state["goal_uuid"]
        rt = ctx.runtime.get(goal_uuid, {})
        rnd = state.get("current_round", 0)
        await ctx.events.publish(goal_uuid, "task.started", {"role": "implementer", "round": rnd})
        await dbio.update_goal_status(ctx.pool, goal_uuid, "executing")

        task_id = await dbio.create_task(ctx.pool, state["goal_id"], "implementer", None)
        prior = state.get("critic_feedback") or {}
        user = (
            f"Issue #{state.get('issue_number')} on {state.get('repo_full_name')}.\n"
            f"Description: {state.get('description','')}\n"
            f"Steering: {state.get('steer','')}\n"
            f"Prior critic feedback: {prior}\n"
            f"Current diff so far:\n{state.get('diff','')[:8000]}"
        )
        res = await ctx.router.acall(
            role="implementer", messages=build_messages(_SYS, user), task_id=task_id, max_tokens=4096
        )
        out = parse_json(res.content, {})
        self_sat = float(out.get("self_satisfaction", 0.0) or 0.0)

        diff = out.get("diff", "")
        handle = rt.get("handle")
        if handle is not None and out.get("files"):
            # apply edits then compute the real diff
            tctx = ToolContext(
                identity=ctx.identity, redis=ctx.redis, sandbox=ctx.sandbox,
                agent_id=rt.get("implementer_agent_id", 0), goal_uuid=goal_uuid,
            )
            fops = FileOpsTool(tctx, handle)
            for f in out["files"]:
                try:
                    await fops.write(f["path"], f.get("content", ""))
                except Exception as e:  # noqa: BLE001
                    log.warning("write failed", path=f.get("path"), err=str(e))
            res_diff = await ctx.sandbox.exec(handle, ["git", "add", "-A"])
            d = await ctx.sandbox.exec(handle, ["git", "diff", "--cached"])
            diff = d.stdout or diff
            _ = res_diff

        await dbio.complete_task(ctx.pool, task_id, {"self_satisfaction": self_sat})
        await dbio.upsert_critic_iteration(
            ctx.pool, state["goal_id"], rnd,
            implementer_prompt={"system": _SYS, "user": user[:2000]},
            implementer_diff=diff, self_satisfaction=self_sat,
        )
        await ctx.events.publish(
            goal_uuid, "iteration.implementer",
            {"round": rnd, "self_satisfaction": self_sat, "summary": out.get("summary", "")},
        )
        return {"diff": diff, "self_satisfaction": self_sat, "current_round": rnd}

    return implementer_node
