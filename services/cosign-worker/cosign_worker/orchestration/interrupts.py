"""HITL gate helpers (ARCHITECTURE §6.6).

loop_exit_node writes the critic_loop_gate interrupt + publishes gate.pending
(runs once). gate_node calls langgraph.interrupt() to suspend the thread; on
resume it returns the human's decision. Keeping the DB/SSE side effects in the
producer node (not gate_node) avoids duplication when LangGraph re-runs the
interrupted node on resume.
"""

from __future__ import annotations

from langgraph.types import interrupt

from . import dbio


def make_loop_exit_node(ctx):
    async def loop_exit_node(state: dict) -> dict:
        goal_uuid = state["goal_uuid"]
        payload = {
            "final_diff": state.get("diff", ""),
            "rounds": state.get("current_round", 0),
            "last_self_satisfaction": state.get("self_satisfaction"),
            "last_critic_feedback": state.get("critic_feedback", {}),
        }
        await dbio.create_interrupt(ctx.pool, state["goal_id"], "critic_loop_gate", payload)
        await dbio.update_goal_status(ctx.pool, goal_uuid, "awaiting_human")
        await ctx.events.publish(goal_uuid, "gate.pending", {"type": "critic_loop_gate"})
        return {"misc": {"gate_payload": payload, "gate_type": "critic_loop_gate"}}

    return loop_exit_node


def make_gate_node(ctx):
    async def gate_node(state: dict) -> dict:
        payload = state.get("misc", {}).get("gate_payload", {})
        resumed = interrupt(payload)  # suspends on first pass; returns resume value
        if isinstance(resumed, dict):
            return {
                "decision": resumed.get("decision", "approve"),
                "misc": {**state.get("misc", {}), "resume": resumed},
            }
        return {"decision": str(resumed or "approve")}

    return gate_node
