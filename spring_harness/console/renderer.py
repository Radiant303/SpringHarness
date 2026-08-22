import json
from collections.abc import AsyncIterable, Awaitable, Callable
from typing import Any

from pydantic_ai import (
    AgentRunResultEvent,
    AgentStreamEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    RunContext,
    TextPartDelta,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturnPart,
)

from spring_harness.console.sink import RenderSink, ToolCallSink


def _args_text(args: object) -> str:
    """把工具参数统一成显示文本。

    边界上宽容接收：实际类型随 pydantic_ai 版本会变（str / dict /
    ToolSearchArgs 等强类型参数对象），这里不枚举，内部分类处理。
    """
    if args is None:
        return ""
    if isinstance(args, str):
        return args
    if isinstance(args, dict):
        return json.dumps(args, ensure_ascii=False)
    return str(args)


class EventStreamRenderer:
    def __init__(self, sink: RenderSink) -> None:
        self._sink = sink
        self._dispatch: dict[type, Callable[[Any], Awaitable[None]]] = {
            PartStartEvent: self._on_part_start,
            PartDeltaEvent: self._on_part_delta,
            PartEndEvent: self._on_part_end,
            FunctionToolResultEvent: self._on_tool_result,
            AgentRunResultEvent: self._on_agent_result,
        }
        self._tool_by_index: dict[int, ToolCallSink] = {}
        self._tool_by_id: dict[str, ToolCallSink] = {}

    async def __call__(
        self,
        ctx: RunContext,
        events: AsyncIterable[AgentStreamEvent | AgentRunResultEvent],
    ) -> None:
        async for event in events:
            handler = self._dispatch.get(type(event))
            if handler is not None:
                await handler(event)

    async def _on_part_start(self, event: PartStartEvent) -> None:
        part = event.part
        if isinstance(part, ToolCallPart):
            tool = await self._sink.start_tool_call(part.tool_name)
            self._tool_by_index[event.index] = tool
            self._tool_by_id[part.tool_call_id] = tool
            if part.args:
                await tool.write_args(_args_text(part.args))

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
        self._tool_by_index.pop(event.index, None)

    async def _on_tool_result(self, event: FunctionToolResultEvent) -> None:
        part = event.part
        if isinstance(part, ToolReturnPart):
            tool = self._tool_by_id.pop(part.tool_call_id, None)
            if tool is not None:
                content = part.content
                await tool.show_result(content if isinstance(content, str) else str(content))

    async def _on_agent_result(self, event: AgentRunResultEvent) -> None:
        await self._sink.finish()
