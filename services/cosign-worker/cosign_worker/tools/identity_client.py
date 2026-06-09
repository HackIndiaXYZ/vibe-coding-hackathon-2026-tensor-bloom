"""gRPC client to cosign-api's IdentityService (capability, OAuth token, audit)."""

from __future__ import annotations

import json

import grpc
import structlog

from ..rpc.pb import orchestration_pb2 as pb2
from ..rpc.pb import orchestration_pb2_grpc as pb2_grpc

log = structlog.get_logger(__name__)


class IdentityClient:
    def __init__(self, addr: str) -> None:
        self._addr = addr
        self._channel: grpc.aio.Channel | None = None
        self._stub: pb2_grpc.IdentityServiceStub | None = None

    async def _ensure(self) -> pb2_grpc.IdentityServiceStub:
        if self._stub is None:
            self._channel = grpc.aio.insecure_channel(self._addr)
            self._stub = pb2_grpc.IdentityServiceStub(self._channel)
        return self._stub

    async def verify_capability(self, agent_id: int, tool_name: str) -> bool:
        stub = await self._ensure()
        resp = await stub.VerifyCapability(
            pb2.VerifyCapabilityRequest(agent_id=agent_id, tool_name=tool_name)
        )
        if not resp.allowed:
            log.warning("capability denied", agent_id=agent_id, tool=tool_name, reason=resp.reason)
        return resp.allowed

    async def get_user_oauth_token(self, user_id: int) -> tuple[str, str]:
        stub = await self._ensure()
        resp = await stub.GetUserOAuthToken(pb2.GetUserOAuthTokenRequest(user_id=user_id))
        return resp.oauth_token, resp.github_login

    async def get_user_llm_settings(self, user_id: int) -> tuple[dict, dict]:
        """Return (routing_overrides, provider_keys) for BYO model selection."""
        import json

        stub = await self._ensure()
        resp = await stub.GetUserLLMSettings(pb2.GetUserLLMSettingsRequest(user_id=user_id))
        try:
            routing = json.loads(resp.routing_json or "{}")
        except json.JSONDecodeError:
            routing = {}
        return routing, dict(resp.provider_keys)

    async def emit_audit_log(
        self, *, actor_type: str, actor_id: int, event_type: str, goal_uuid: str, payload: dict
    ) -> None:
        stub = await self._ensure()
        await stub.EmitAuditLog(
            pb2.EmitAuditLogRequest(
                actor_type=actor_type,
                actor_id=actor_id,
                event_type=event_type,
                goal_uuid=goal_uuid,
                payload_json=json.dumps(payload),
            )
        )

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
