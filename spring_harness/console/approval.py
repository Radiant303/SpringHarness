from collections.abc import Awaitable, Callable
from typing import Any

from pydantic_ai import Agent, AgentRunResult, ToolCallPart
from pydantic_ai.tools import DeferredToolApprovalResult, DeferredToolRequests

from spring_harness.console.renderer import EventStreamRenderer


async def run_with_approval(
    agent: Agent[Any, Any],
    prompt: str,
    renderer: EventStreamRenderer,
    ask: Callable[[ToolCallPart], Awaitable[bool]],
) -> AgentRunResult[Any]:
    result = await agent.run(prompt,event_stream_handler=renderer)
    while isinstance(result.output, DeferredToolRequests):
        approvals: dict[str, DeferredToolApprovalResult | bool] = {}
        requests = result.output
        assert not requests.calls
        for call in requests.approvals:
            ask_result = await ask(call)
            approvals[call.tool_call_id] = ask_result
        results = requests.build_results(approvals=approvals)
        result = await agent.run(None, message_history=result.all_messages(),deferred_tool_results=results, event_stream_handler=renderer)

    await renderer.finish_with(result)
    return result
