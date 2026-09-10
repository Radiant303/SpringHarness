from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pydantic_ai import (
    Agent,
    AgentRunResult,
    CancellationToken,
    ModelMessage,
    ModelRetry,
    ToolCallPart,
    ToolFailed,
)
from pydantic_ai.tools import DeferredToolApprovalResult, DeferredToolRequests

from spring_harness.console.renderer import EventStreamRenderer
from spring_harness.core.agent.deps import CodingAgentDeps


async def run_with_approval(
    agent: Agent[Any, Any],
    prompt: str,
    renderer: EventStreamRenderer,
    ask: Callable[[ToolCallPart], Awaitable[bool]],
    ask_question: Callable[[dict[str, Any]], Awaitable[str | None]],
    deps: CodingAgentDeps,
    message_history: Sequence[ModelMessage] | None = None,
    cancellation_token: CancellationToken | None = None,
) -> AgentRunResult[Any]:
    result = await agent.run(
        prompt,
        deps=deps,
        event_stream_handler=renderer,
        message_history=message_history,
        cancellation_token=cancellation_token,
    )
    while isinstance(result.output, DeferredToolRequests):
        approvals: dict[str, DeferredToolApprovalResult | bool] = {}
        requests = result.output
        calls: dict[str, Any] = {}
        for call in requests.calls:
            if call.tool_name == "ask_user":
                answer = await ask_question(call.args_as_dict())
                if answer is None:
                    calls[call.tool_call_id] = ModelRetry("用户取消了提问，请自行判断或换个问法")
                else:
                    calls[call.tool_call_id] = answer
            else:
                calls[call.tool_call_id] = ToolFailed(f"未知的外部执行工具: {call.tool_name}")
        for call in requests.approvals:
            ask_result = await ask(call)
            approvals[call.tool_call_id] = ask_result
        results = requests.build_results(approvals=approvals, calls=calls)
        result = await agent.run(
            None,
            deps=deps,
            message_history=result.all_messages(),
            deferred_tool_results=results,
            event_stream_handler=renderer,
            cancellation_token=cancellation_token,
        )

    await renderer.finish_with(result)
    return result
