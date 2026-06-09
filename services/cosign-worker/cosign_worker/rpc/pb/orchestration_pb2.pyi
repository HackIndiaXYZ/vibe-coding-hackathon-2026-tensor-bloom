from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class SubmitGoalRequest(_message.Message):
    __slots__ = ("goal_uuid",)
    GOAL_UUID_FIELD_NUMBER: _ClassVar[int]
    goal_uuid: str
    def __init__(self, goal_uuid: _Optional[str] = ...) -> None: ...

class SubmitGoalResponse(_message.Message):
    __slots__ = ("accepted", "message")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    message: str
    def __init__(self, accepted: _Optional[bool] = ..., message: _Optional[str] = ...) -> None: ...

class ResumeFromInterruptRequest(_message.Message):
    __slots__ = ("goal_uuid", "decision", "feedback", "edited_payload_json")
    GOAL_UUID_FIELD_NUMBER: _ClassVar[int]
    DECISION_FIELD_NUMBER: _ClassVar[int]
    FEEDBACK_FIELD_NUMBER: _ClassVar[int]
    EDITED_PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    goal_uuid: str
    decision: str
    feedback: str
    edited_payload_json: str
    def __init__(self, goal_uuid: _Optional[str] = ..., decision: _Optional[str] = ..., feedback: _Optional[str] = ..., edited_payload_json: _Optional[str] = ...) -> None: ...

class ResumeFromInterruptResponse(_message.Message):
    __slots__ = ("accepted", "message")
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    message: str
    def __init__(self, accepted: _Optional[bool] = ..., message: _Optional[str] = ...) -> None: ...

class CancelGoalRequest(_message.Message):
    __slots__ = ("goal_uuid",)
    GOAL_UUID_FIELD_NUMBER: _ClassVar[int]
    goal_uuid: str
    def __init__(self, goal_uuid: _Optional[str] = ...) -> None: ...

class CancelGoalResponse(_message.Message):
    __slots__ = ("cancelled",)
    CANCELLED_FIELD_NUMBER: _ClassVar[int]
    cancelled: bool
    def __init__(self, cancelled: _Optional[bool] = ...) -> None: ...

class VerifyCapabilityRequest(_message.Message):
    __slots__ = ("agent_id", "tool_name")
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    TOOL_NAME_FIELD_NUMBER: _ClassVar[int]
    agent_id: int
    tool_name: str
    def __init__(self, agent_id: _Optional[int] = ..., tool_name: _Optional[str] = ...) -> None: ...

class VerifyCapabilityResponse(_message.Message):
    __slots__ = ("allowed", "reason")
    ALLOWED_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    allowed: bool
    reason: str
    def __init__(self, allowed: _Optional[bool] = ..., reason: _Optional[str] = ...) -> None: ...

class GetUserOAuthTokenRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    def __init__(self, user_id: _Optional[int] = ...) -> None: ...

class GetUserOAuthTokenResponse(_message.Message):
    __slots__ = ("oauth_token", "github_login")
    OAUTH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    GITHUB_LOGIN_FIELD_NUMBER: _ClassVar[int]
    oauth_token: str
    github_login: str
    def __init__(self, oauth_token: _Optional[str] = ..., github_login: _Optional[str] = ...) -> None: ...

class EmitAuditLogRequest(_message.Message):
    __slots__ = ("actor_type", "actor_id", "event_type", "goal_uuid", "payload_json")
    ACTOR_TYPE_FIELD_NUMBER: _ClassVar[int]
    ACTOR_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    GOAL_UUID_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    actor_type: str
    actor_id: int
    event_type: str
    goal_uuid: str
    payload_json: str
    def __init__(self, actor_type: _Optional[str] = ..., actor_id: _Optional[int] = ..., event_type: _Optional[str] = ..., goal_uuid: _Optional[str] = ..., payload_json: _Optional[str] = ...) -> None: ...

class EmitAuditLogResponse(_message.Message):
    __slots__ = ("ok",)
    OK_FIELD_NUMBER: _ClassVar[int]
    ok: bool
    def __init__(self, ok: _Optional[bool] = ...) -> None: ...

class GetUserLLMSettingsRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    def __init__(self, user_id: _Optional[int] = ...) -> None: ...

class GetUserLLMSettingsResponse(_message.Message):
    __slots__ = ("routing_json", "provider_keys")
    class ProviderKeysEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ROUTING_JSON_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_KEYS_FIELD_NUMBER: _ClassVar[int]
    routing_json: str
    provider_keys: _containers.ScalarMap[str, str]
    def __init__(self, routing_json: _Optional[str] = ..., provider_keys: _Optional[_Mapping[str, str]] = ...) -> None: ...
