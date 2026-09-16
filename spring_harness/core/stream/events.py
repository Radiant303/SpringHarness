from typing import Literal

from pydantic import BaseModel


class TextDelta(BaseModel):
    kind: Literal["text_delta"] = "text_delta"
    text: str

class ThinkingDelta(BaseModel):
    kind: Literal["thinking_delta"] = "thinking_delta"
    text: str

class ToolCallStarted(BaseModel):
    kind: Literal["tool_started"] = "tool_started"
    tool_call_id: str
    tool_name: str

class ToolArgsDelta(BaseModel):
    kind: Literal["tool_args_delta"] = "tool_args_delta"
    tool_call_id: str
    args_chunk: str

class ToolDiff(BaseModel):
    kind: Literal["tool_diff"] = "tool_diff"
    tool_call_id: str
    diff: str

class ToolFinished(BaseModel):
    kind: Literal["tool_finished"] = "tool_finished"
    tool_call_id: str
    result: str
    is_error: bool = False

class ToolPending(BaseModel):
    kind: Literal["tool_pending"] = "tool_pending"
    tool_call_id: str
    label: str = "等待批准"

class UsageUpdated(BaseModel):
    kind: Literal["usage"] = "usage"
    context_tokens: int

class PlanUpdated(BaseModel):
    kind: Literal["plan_updated"] = "plan_updated"
    items: list[dict]

class TeachingUpdated(BaseModel):
    kind: Literal["teaching_updated"] = "teaching_updated"
    unit: dict

class CompactionNotice(BaseModel):
    kind: Literal["compaction"] = "compaction"
    dropped: int; before: int; after: int

class TurnFinished(BaseModel):
    kind: Literal["turn_finished"] = "turn_finished"
    cancelled: bool = False
    error: str | None = None
    wake: bool = False  # True = 后台任务催醒轮（前端可据此区分系统轮次）

class BackgroundTaskStarted(BaseModel):
    kind: Literal["background_task_started"] = "background_task_started"
    task_id: str
    tool_name: str
    args: dict

class BackgroundTaskFinished(BaseModel):
    kind: Literal["background_task_finished"] = "background_task_finished"
    task_id: str
    tool_name: str
    result: str
    is_error: bool = False
    cancelled: bool = False

class ApprovalRequest(BaseModel):
    kind: Literal["approval_request"] = "approval_request"
    request_id: str
    tool_call_id: str
    tool_name: str
    args: dict
    diff: str | None

class QuestionRequest(BaseModel):
    kind: Literal["question_request"] = "question_request"
    request_id: str
    question: str
    options: list | None
    allow_custom: bool = True


ServerEvent = TextDelta | ThinkingDelta | ToolCallStarted | ToolArgsDelta | ToolDiff | ToolPending | ToolFinished | UsageUpdated | PlanUpdated | TeachingUpdated | CompactionNotice | TurnFinished | ApprovalRequest | QuestionRequest | BackgroundTaskStarted | BackgroundTaskFinished
