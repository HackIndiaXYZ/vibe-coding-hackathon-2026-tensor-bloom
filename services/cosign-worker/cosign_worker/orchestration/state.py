"""AgentState — the LangGraph state (checkpointed to Postgres).

IMPORTANT: only JSON-serializable, non-sensitive scalars live here. The user's
OAuth token and the live SandboxHandle are kept in an in-memory runtime registry
(ctx.runtime[goal_uuid]) so they are never written to the checkpoint store.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    # identity / target
    goal_id: int
    goal_uuid: str
    goal_type: str  # pr_review | issue_implement
    user_id: int
    repo_full_name: str  # owner/repo
    pr_number: int | None
    issue_number: int | None
    fork_mode: bool
    steer: str
    default_branch: str
    work_branch: str

    # planning
    plan: list[str]

    # Flow B critic loop
    diff: str
    self_satisfaction: float
    critic_feedback: dict
    current_round: int
    max_iters: int
    threshold: float

    # Flow A review
    review_draft: dict

    # resolution
    decision: str
    output_url: str

    # llm message log (LangGraph reducer)
    messages: Annotated[list, add_messages]
    misc: dict[str, Any]
