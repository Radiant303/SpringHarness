import asyncio
from typing import Any

from pydantic_ai import (
    AgentRunResult,
    ModelRequest,
    ModelRequestContext,
    ModelResponse,
    RunContext,
    UserPromptPart,
)
from pydantic_ai.capabilities import Hooks

from spring_harness.core.agent.deps import CodingAgentDeps

hooks = Hooks()

@hooks.on.after_run
async def start_monitor(
    ctx: RunContext[CodingAgentDeps],
    *,
    result: AgentRunResult[Any],
) -> AgentRunResult[Any]:
    await asyncio.to_thread(ctx.deps.monitor.start)
    return result


FILE_MONITOR_SOURCE = "file_monitor"
BACKGROUND_TASK_SOURCE = "background_task"
BACKGROUND_WAKE_SOURCE = "background_wake"

_AUTO_INJECTED_SOURCES = {FILE_MONITOR_SOURCE, BACKGROUND_TASK_SOURCE, BACKGROUND_WAKE_SOURCE}


def is_file_monitor_message(message: object) -> bool:
    """判断一条消息是否是由 file_monitor 自动注入的文件变动通知。"""
    metadata = getattr(message, "metadata", None)
    return isinstance(metadata, dict) and metadata.get("source") == FILE_MONITOR_SOURCE


def is_background_task_message(message: object) -> bool:
    """判断一条消息是否是后台任务相关（结果注入或催醒轮 prompt）。"""
    metadata = getattr(message, "metadata", None)
    return isinstance(metadata, dict) and metadata.get("source") in {
        BACKGROUND_TASK_SOURCE,
        BACKGROUND_WAKE_SOURCE,
    }


def is_auto_injected_message(message: object) -> bool:
    """判断一条消息是否是系统自动注入的（文件变动/后台任务），而非真实用户输入。"""
    metadata = getattr(message, "metadata", None)
    return isinstance(metadata, dict) and metadata.get("source") in _AUTO_INJECTED_SOURCES


@hooks.on.before_model_request
async def stop_monitor(
    ctx: RunContext[CodingAgentDeps],
    request_context: ModelRequestContext
) -> ModelRequestContext:
    changes = await asyncio.to_thread(ctx.deps.monitor.stop)
    changes_text = ctx.deps.monitor.changes_to_string(changes)
    if changes_text is not None:
        request_context.messages.append(
            ModelRequest(
                parts=[UserPromptPart(changes_text)],
                metadata={"source": FILE_MONITOR_SOURCE},
            )
        )
    ctx.deps.last_messages = list(request_context.messages)
    return request_context

@hooks.on.after_model_request
async def log_request_usage(
    ctx: RunContext[CodingAgentDeps],
    *,
    request_context: ModelRequestContext,
    response: ModelResponse,
) -> ModelResponse:
    ctx.deps.usage_log.append(response.usage)
    return response
