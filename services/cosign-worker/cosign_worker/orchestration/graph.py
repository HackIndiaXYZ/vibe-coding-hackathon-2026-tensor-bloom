"""Build the LangGraph StateGraph and wire run/resume/cancel onto the context.

Graph (both flows share plan + gate + finalize):

    START -> plan -> (pr_review)      reviewer ----------------\
                  -> (issue_implement) implementer <-> critic   |
                                          |  (converged/max)    |
                                          v                     v
                                       loop_exit ----------> gate -> finalize -> END
                                                              ^ (revise routes back to producer)
"""

from __future__ import annotations

import asyncio

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from . import dbio
from .events import EventPublisher
from .interrupts import make_gate_node, make_loop_exit_node
from .nodes.critic import make_critic_node
from .nodes.finalize import make_finalize_node
from .nodes.implementer import make_implementer_node
from .nodes.plan import make_plan_node
from .nodes.reviewer import make_reviewer_node
from .state import AgentState

log = structlog.get_logger(__name__)

_DEFAULT_THRESHOLD = 0.85
_DEFAULT_MAX_ITERS = 5
_bg_tasks: set[asyncio.Task] = set()


def _route_after_plan(state: dict) -> str:
    return "reviewer" if state.get("goal_type") == "pr_review" else "implementer"


def _should_continue(state: dict) -> str:
    """implementer -> exit | critic (self-satisfaction threshold OR max-iter cap)."""
    if state.get("self_satisfaction", 0.0) >= state.get("threshold", _DEFAULT_THRESHOLD):
        return "exit"
    if state.get("current_round", 0) + 1 >= state.get("max_iters", _DEFAULT_MAX_ITERS):
        return "exit"
    return "critic"


def _route_after_gate(state: dict) -> str:
    decision = state.get("decision", "approve")
    if decision == "revise":
        return "reviewer" if state.get("goal_type") == "pr_review" else "implementer"
    return "finalize"


def build_graph(ctx):
    g = StateGraph(AgentState)
    g.add_node("plan", make_plan_node(ctx))
    g.add_node("reviewer", make_reviewer_node(ctx))
    g.add_node("implementer", make_implementer_node(ctx))
    g.add_node("critic", make_critic_node(ctx))
    g.add_node("loop_exit", make_loop_exit_node(ctx))
    g.add_node("gate", make_gate_node(ctx))
    g.add_node("finalize", make_finalize_node(ctx))

    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", _route_after_plan,
                            {"reviewer": "reviewer", "implementer": "implementer"})
    g.add_edge("reviewer", "gate")
    g.add_conditional_edges("implementer", _should_continue,
                            {"critic": "critic", "exit": "loop_exit"})
    g.add_edge("critic", "implementer")
    g.add_edge("loop_exit", "gate")
    g.add_conditional_edges("gate", _route_after_gate,
                            {"finalize": "finalize", "reviewer": "reviewer", "implementer": "implementer"})
    g.add_edge("finalize", END)
    return g


async def attach_orchestration(ctx) -> None:
    """Compile the graph with a Postgres checkpointer and install run/resume/cancel."""
    if ctx.events is None:
        ctx.events = EventPublisher(ctx.redis)

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    conn = ctx.config.database_url.replace("postgres://", "postgresql://")
    cm = AsyncPostgresSaver.from_conn_string(conn)
    saver = await cm.__aenter__()
    await saver.setup()
    ctx.checkpointer = saver
    ctx._checkpointer_cm = cm  # keep ref so it isn't GC'd
    ctx.graph = build_graph(ctx).compile(checkpointer=saver)

    ctx.run_goal = _make_run_goal(ctx)
    ctx.resume_goal = _make_resume_goal(ctx)
    ctx.cancel_goal = _make_cancel_goal(ctx)
    log.info("orchestration attached")


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _make_run_goal(ctx):
    async def run_goal(goal_uuid: str) -> None:
        _spawn(_run(ctx, goal_uuid))

    return run_goal


def _make_resume_goal(ctx):
    async def resume_goal(goal_uuid: str, decision: str, feedback: str, edited: str) -> None:
        _spawn(_resume(ctx, goal_uuid, decision, feedback, edited))

    return resume_goal


def _make_cancel_goal(ctx):
    async def cancel_goal(goal_uuid: str) -> None:
        await dbio.update_goal_status(ctx.pool, goal_uuid, "cancelled")
        rt = ctx.runtime.pop(goal_uuid, {})
        if rt.get("handle"):
            try:
                await ctx.sandbox.stop(rt["handle"])
            except Exception:  # noqa: BLE001
                pass

    return cancel_goal


async def _bootstrap_runtime(ctx, goal) -> dict:
    """Fetch the user's OAuth token + (for issue flow) clone the repo into a sandbox."""
    rt: dict = {"login": "", "token": "", "handle": None,
                "implementer_agent_id": 1, "reviewer_agent_id": 2}
    # user OAuth token (acts AS the user). Best-effort: missing api/keys -> mock dev run.
    if ctx.identity is not None:
        try:
            token, login = await ctx.identity.get_user_oauth_token(goal.user_id)
            rt["token"], rt["login"] = token, login
        except Exception as e:  # noqa: BLE001
            log.warning("token fetch failed; continuing without (dev/mock)", err=str(e))

    if goal.type == "issue_implement" and rt["token"] and goal.repo_full_name:
        owner, repo = goal.repo_full_name.split("/", 1)
        repo_url = f"https://github.com/{owner}/{repo}.git"
        try:
            handle = await ctx.sandbox.start(
                task_id=goal.uuid[:8], image=ctx.config.sandbox_image,
                repo_url=repo_url, branch="", github_token=rt["token"], timeout_s=120,
            )
            rt["handle"] = handle
        except Exception as e:  # noqa: BLE001
            log.warning("sandbox clone failed; continuing without", err=str(e))
    return rt


async def _run(ctx, goal_uuid: str) -> None:
    goal = await dbio.load_goal(ctx.pool, goal_uuid)
    if goal is None:
        log.error("run: goal not found", goal_uuid=goal_uuid)
        return
    try:
        rt = await _bootstrap_runtime(ctx, goal)
        ctx.runtime[goal_uuid] = rt
        branch = f"cosign/issue-{goal.issue_number}" if goal.issue_number else "cosign/work"
        initial: dict = {
            "goal_id": goal.id, "goal_uuid": goal.uuid, "goal_type": goal.type,
            "user_id": goal.user_id, "repo_full_name": goal.repo_full_name,
            "pr_number": goal.pr_number, "issue_number": goal.issue_number,
            "fork_mode": goal.fork_mode, "description": goal.description or "",
            "steer": (goal.description or ""), "default_branch": "main", "work_branch": branch,
            "current_round": 0, "max_iters": _DEFAULT_MAX_ITERS, "threshold": _DEFAULT_THRESHOLD,
            "diff": "", "self_satisfaction": 0.0, "critic_feedback": {}, "misc": {},
        }
        config = {"configurable": {"thread_id": goal_uuid}}
        await ctx.graph.ainvoke(initial, config)  # runs to the gate (interrupt) or END
    except Exception as e:  # noqa: BLE001
        log.error("run_goal failed", goal_uuid=goal_uuid, err=str(e))
        await dbio.update_goal_status(ctx.pool, goal_uuid, "failed")
        await ctx.events.publish(goal_uuid, "goal.failed", {"error": str(e)})


async def _resume(ctx, goal_uuid: str, decision: str, feedback: str, edited: str) -> None:
    try:
        config = {"configurable": {"thread_id": goal_uuid}}
        resume_val = {"decision": decision, "feedback": feedback, "edited_payload": edited}
        await ctx.graph.ainvoke(Command(resume=resume_val), config)
    except Exception as e:  # noqa: BLE001
        log.error("resume_goal failed", goal_uuid=goal_uuid, err=str(e))
        await dbio.update_goal_status(ctx.pool, goal_uuid, "failed")
        await ctx.events.publish(goal_uuid, "goal.failed", {"error": str(e)})
    finally:
        # terminal decisions clean up the sandbox
        if decision in ("approve", "reject"):
            rt = ctx.runtime.pop(goal_uuid, {})
            if rt.get("handle"):
                try:
                    await ctx.sandbox.stop(rt["handle"])
                except Exception:  # noqa: BLE001
                    pass
