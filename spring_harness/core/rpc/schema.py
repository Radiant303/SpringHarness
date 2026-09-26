from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _WireModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class WorkspaceParams(_WireModel):
    workspace: str
    model: str | None = None


class SessionParams(_WireModel):
    session_id: str = Field(validation_alias="sessionId", serialization_alias="sessionId")


class AttachParams(_WireModel):
    workspace: str
    session_id: str = Field(validation_alias="sessionId", serialization_alias="sessionId")
    model: str | None = None


class TurnStartParams(_WireModel):
    session_id: str = Field(validation_alias="sessionId", serialization_alias="sessionId")
    input: str


class SetModelParams(_WireModel):
    session_id: str = Field(validation_alias="sessionId", serialization_alias="sessionId")
    model: str


class InitializeResult(_WireModel):
    server_name: str = Field(validation_alias="serverName", serialization_alias="serverName")
    protocol_version: int = Field(validation_alias="protocolVersion", serialization_alias="protocolVersion")


class SessionResult(_WireModel):
    session_id: str | None = Field(validation_alias="sessionId", serialization_alias="sessionId")


class SessionSummary(_WireModel):
    session_id: str = Field(validation_alias="sessionId", serialization_alias="sessionId")
    title: str | None = None
    created_at: str = Field(validation_alias="createdAt", serialization_alias="createdAt")
    updated_at: str | None = Field(default=None, validation_alias="updatedAt", serialization_alias="updatedAt")


class SessionListResult(_WireModel):
    sessions: list[SessionSummary]


class HistoryQueryParams(_WireModel):
    """按消息数查询历史，结果始终正序；空游标从指定方向的端点开始。

    limit=None 返回完整当前历史且不能携带 cursor。
    nextCursor 向前续取，previousCursor 向后续取；hasMore 对应请求方向。
    游标固定存储快照，重新传空游标才能看到后续追加的历史。
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(validation_alias="sessionId", serialization_alias="sessionId")
    cursor: str | None = None
    limit: int | None = Field(default=None, ge=1, strict=True)
    direction: Literal["forward", "backward"] = "forward"


class HistoryResult(_WireModel):
    segments: list[list[dict]]
    first_segment_index: int | None = Field(
        default=None, ge=0, validation_alias="firstSegmentIndex", serialization_alias="firstSegmentIndex",
    )
    next_cursor: str | None = Field(default=None, validation_alias="nextCursor", serialization_alias="nextCursor")
    previous_cursor: str | None = Field(default=None, validation_alias="previousCursor", serialization_alias="previousCursor")
    has_more: bool = Field(validation_alias="hasMore", serialization_alias="hasMore")


class PlanResult(_WireModel):
    items: list[dict]


class SessionEventParams(_WireModel):
    session_id: str = Field(validation_alias="sessionId", serialization_alias="sessionId")
    event: dict


class ApprovalRequestParams(_WireModel):
    session_id: str = Field(validation_alias="sessionId", serialization_alias="sessionId")
    tool_call_id: str = Field(validation_alias="toolCallId", serialization_alias="toolCallId")
    tool_name: str = Field(validation_alias="toolName", serialization_alias="toolName")
    args: dict
    diff: str | None


class QuestionRequestParams(_WireModel):
    session_id: str = Field(validation_alias="sessionId", serialization_alias="sessionId")
    question: str
    options: list | None
    allow_custom: bool = Field(validation_alias="allowCustom", serialization_alias="allowCustom")


class ApprovalResult(_WireModel):
    approved: bool = False


class QuestionResult(_WireModel):
    answer: str | None = None
