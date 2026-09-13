import asyncio
import json
from collections.abc import AsyncIterable, Awaitable, Callable
from typing import Any

from pydantic_ai import (
    AgentRunResult,
    AgentRunResultEvent,
    AgentStreamEvent,
    DeferredToolRequestsEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    RetryPromptPart,
    RunContext,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturnPart,
)

from spring_harness.core.agent.deps import CodingAgentDeps
from spring_harness.core.stream.sink import ToolCallSink, TurnSink
from spring_harness.utils.diff import make_diff


def _args_text(args: object) -> str:
    if args is None:
        return ""
    if isinstance(args, str):
        return args
    if isinstance(args, dict):
        return json.dumps(args, ensure_ascii=False)
    return str(args)


class AgentEventAdapter:
    def __init__(self, sink: TurnSink) -> None:
        self._sink: TurnSink = sink
        self._dispatch: dict[type, Callable[[Any], Awaitable[None]]] = {
            PartStartEvent: self._on_part_start,
            PartDeltaEvent: self._on_part_delta,
            PartEndEvent: self._on_part_end,
            FunctionToolResultEvent: self._on_tool_result,
            DeferredToolRequestsEvent: self._on_deferred_requests,
            AgentRunResultEvent: self._on_agent_result,
        }
        self._tool_by_index: dict[int, ToolCallSink] = {}
        self._tool_by_id: dict[str, ToolCallSink] = {}
        self._context = 0  # 最近一场 run 的 token 用量（input+output ≈ 当前上下文占用）
        self._last_usage: int | None = None

    async def __call__(
        self,
        _ctx: RunContext[object] | None,
        events: AsyncIterable[AgentStreamEvent | AgentRunResultEvent],
    ) -> None:
        async for event in events:
            handler = self._dispatch.get(type(event))
            if handler is not None:
                await handler(event)
            if _ctx is not None and isinstance(_ctx.deps, CodingAgentDeps) and _ctx.deps.usage_log:
                usage = _ctx.deps.usage_log[-1]
                tokens = usage.input_tokens + usage.output_tokens
                if tokens != self._last_usage:
                    self._last_usage = tokens
                    await self._sink.update_context(tokens)

    async def _on_part_start(self, event: PartStartEvent) -> None:
        part = event.part
        if isinstance(part, ToolCallPart):
            tool = await self._sink.start_tool_call(part.tool_name, part.tool_call_id)
            self._tool_by_index[event.index] = tool
            self._tool_by_id[part.tool_call_id] = tool
            if part.args:
                await tool.write_args(_args_text(part.args))
        elif isinstance(part, ThinkingPart) and part.content:
            # 首口内容在 start 事件里，不写就吞了首 token
            await self._sink.write_thinking(part.content)
        elif isinstance(part, TextPart) and part.content:
            await self._sink.write_answer(part.content)

    async def _on_part_delta(self, event: PartDeltaEvent) -> None:
        delta = event.delta
        if isinstance(delta, ThinkingPartDelta) and delta.content_delta:
            await self._sink.write_thinking(delta.content_delta)
        elif isinstance(delta, TextPartDelta) and delta.content_delta:
            await self._sink.write_answer(delta.content_delta)
        elif isinstance(delta, ToolCallPartDelta) and delta.args_delta:
            tool = self._tool_by_index.get(event.index)
            if tool is not None:
                await tool.write_args(_args_text(delta.args_delta))

    async def _on_part_end(self, event: PartEndEvent) -> None:
        tool = self._tool_by_index.pop(event.index, None)
        part = event.part
        if tool is not None and isinstance(part, ToolCallPart):
            # 大文件的 unified_diff 可能耗时几十到几百毫秒，挪线程避免阻塞事件循环
            diff = await asyncio.to_thread(make_diff, part.tool_name, part.args)
            if diff is not None:
                await tool.show_diff(diff)

    async def _on_deferred_requests(self, event: DeferredToolRequestsEvent) -> None:
        calls = event.requests.calls
        approvals = event.requests.approvals

        for call_part in calls:
            tool = self._tool_by_id.get(call_part.tool_call_id)
            if tool is not None:
                await tool.show_pending("等待回答")

        for approvals_part in approvals:
            tool = self._tool_by_id.get(approvals_part.tool_call_id)
            if tool is not None:
                await tool.show_pending()

    async def _on_tool_result(self, event: FunctionToolResultEvent) -> None:
        part = event.part
        if not isinstance(part, ToolReturnPart | RetryPromptPart):
            return
        tool = self._tool_by_id.pop(part.tool_call_id, None)
        if tool is not None:
            # RetryPromptPart = 工具执行/参数校验失败，框架会让模型重试
            content = part.content
            await tool.show_result(
                content if isinstance(content, str) else str(content),
                is_error=isinstance(part, RetryPromptPart),
            )

    async def _on_agent_result(self, event: AgentRunResultEvent) -> None:
        result = event.result
        if result is not None and result.response is not None:
            usage = result.response.usage
            input_token = usage.input_tokens
            output_token = usage.output_tokens
            self._context = input_token + output_token
            await self._sink.update_context(self._context)
            try:
                # response_text = result.response.text
                pass
            except ValueError:
                pass
                # response_text = str(result.output)
        await self._sink.finish()

    async def finish_with(self, result: AgentRunResult) -> None:
        await self._on_agent_result(AgentRunResultEvent(result=result))
