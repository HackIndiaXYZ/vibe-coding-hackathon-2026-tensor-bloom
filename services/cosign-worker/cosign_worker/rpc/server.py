"""gRPC OrchestrationService — entrypoint cosign-api calls to drive agent runs.

Phase 3 ships stubs that accept calls and log; the LangGraph wiring lands in
Phase 5. The servicer holds the shared worker context (pool, redis, router,
sandbox driver) so nodes can be dispatched later.
"""

from __future__ import annotations

import structlog

from .pb import orchestration_pb2 as pb2
from .pb import orchestration_pb2_grpc as pb2_grpc

log = structlog.get_logger(__name__)


class OrchestrationServicer(pb2_grpc.OrchestrationServiceServicer):
    def __init__(self, ctx) -> None:
        self.ctx = ctx  # WorkerContext (pool, redis, router, sandbox)

    async def SubmitGoal(self, request, context):  # noqa: N802 (grpc naming)
        log.info("SubmitGoal", goal_uuid=request.goal_uuid)
        # Phase 5: load goal, build graph, start thread.
        if self.ctx.run_goal is not None:
            await self.ctx.run_goal(request.goal_uuid)
            return pb2.SubmitGoalResponse(accepted=True, message="started")
        return pb2.SubmitGoalResponse(accepted=False, message="orchestration not wired yet")

    async def ResumeFromInterrupt(self, request, context):  # noqa: N802
        log.info("ResumeFromInterrupt", goal_uuid=request.goal_uuid, decision=request.decision)
        if self.ctx.resume_goal is not None:
            await self.ctx.resume_goal(
                request.goal_uuid, request.decision, request.feedback, request.edited_payload_json
            )
            return pb2.ResumeFromInterruptResponse(accepted=True, message="resumed")
        return pb2.ResumeFromInterruptResponse(accepted=False, message="orchestration not wired yet")

    async def CancelGoal(self, request, context):  # noqa: N802
        log.info("CancelGoal", goal_uuid=request.goal_uuid)
        if self.ctx.cancel_goal is not None:
            await self.ctx.cancel_goal(request.goal_uuid)
        return pb2.CancelGoalResponse(cancelled=True)
