"""批准循环：run → DeferredToolRequests → ask → 续跑（考卷——由你完成）。

规格：``run_with_approval(agent, prompt, event_stream_handler, ask)``

- 调用 ``agent.run(prompt, event_stream_handler=event_stream_handler)``；
- 若 ``result.output`` 是 ``DeferredToolRequests``（有调用被挂起）：
  1. **逐条问**：对 ``requests.approvals`` 里的每个 ``ToolCallPart``，
     ``ok = await ask(call)``，攒出 ``{call.tool_call_id: ok}`` 字典；
  2. 用 ``requests.build_results(approvals=那个字典)`` 造出结果；
  3. 续跑：``agent.run(None, message_history=result.all_messages(),
     deferred_tool_results=results, event_stream_handler=event_stream_handler)``；
  4. 回到第 2 步判断——批准的调用可能引出新的挂起调用，所以要循环不要 if；
- 否则（output 是正文 str）循环结束，返回最后的 result；
- 全程用同一个 ``event_stream_handler``：续跑的 FunctionToolResultEvent 靠
  同一个 tool_call_id 找回等待中的卡片，换了 renderer 卡片就永远停在"等待批准"。
- 已知边界：``requests.calls``（外部执行类挂起）本考试不处理——我们的
  agent 配置只产生 approvals；遇到了直接 ``assert not requests.calls`` 即可。

已实测的事实（TestModel 验证过，放心依赖）：
- 批准：续跑的事件流里有 FunctionToolResultEvent，工具真执行了；
- 拒绝：也有，content 是 "The tool call was denied."；
- 两条路可以混：同一批里 edit 批准、write 拒绝，各走各的结果；
- 续跑时 user_prompt 传 None 即可（message_history 已带上下文）。

判卷：.venv/Scripts/python.exe test_console.py 十二个全绿，且编辑器无红线。
"""

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
