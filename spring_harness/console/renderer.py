import difflib
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
    RunContext,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturnPart,
)

from spring_harness.console.sink import RenderSink, ToolCallSink
from spring_harness.core.log import logger


def _args_text(args: object) -> str:
    if args is None:
        return ""
    if isinstance(args, str):
        return args
    if isinstance(args, dict):
        return json.dumps(args, ensure_ascii=False)
    return str(args)


def _make_diff(tool_name: str, args: object) -> str | None:
    """编辑类工具的调用参数 → unified diff 文本；其它工具或参数不全返回 None。

    diff 展示的是"打算怎么改"（来自调用参数而非执行结果），
    所以在 args 完整的那一刻（PartEndEvent）生成，不等工具返回。
    """
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return None
    if not isinstance(args, dict):
        return None
    path = str(args.get("path", ""))
    if tool_name == "edit_file":
        old, new = args.get("old_text"), args.get("new_text")
        if isinstance(old, str) and isinstance(new, str):
            return "".join(difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{path}", tofile=f"b/{path}",
            ))
    elif tool_name == "write_file":
        content = args.get("content")
        if isinstance(content, str):
            return "".join(difflib.unified_diff(
                [], content.splitlines(keepends=True),
                fromfile="/dev/null", tofile=f"b/{path}",
            ))
    return None


class EventStreamRenderer:
    def __init__(self, sink: RenderSink) -> None:
        self._sink:RenderSink = sink
        self._dispatch: dict[type, Callable[[Any], Awaitable[None]]] = {
            PartStartEvent: self._on_part_start,
            PartDeltaEvent: self._on_part_delta,
            PartEndEvent: self._on_part_end,
            FunctionToolResultEvent: self._on_tool_result,
            DeferredToolRequestsEvent:self._on_deferred_requests,
            AgentRunResultEvent: self._on_agent_result,
        }
        self._tool_by_index: dict[int, ToolCallSink] = {}
        self._tool_by_id: dict[str, ToolCallSink] = {}
        self._context = 0  # 最近一场 run 的 token 用量（input+output ≈ 当前上下文占用）

    async def __call__(
        self,
        _ctx: RunContext[object] | None,
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
        elif isinstance(part, ThinkingPart) and part.content:
            # 第一口内容在 start 事件里，不写就吞了首 token
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
            diff = _make_diff(part.tool_name, part.args)
            if diff is not None:
                await tool.show_diff(diff)

    async def _on_deferred_requests(self, event: DeferredToolRequestsEvent) -> None:
        calls = event.requests.calls
        approvals = event.requests.approvals

        for call_part in calls:
            tool = self._tool_by_id.get(call_part.tool_call_id)
            if tool is not None:
                await tool.show_pending()

        for approvals_part in approvals:
            tool = self._tool_by_id.get(approvals_part.tool_call_id)
            if tool is not None:
                await tool.show_pending()


    async def _on_tool_result(self, event: FunctionToolResultEvent) -> None:
        part = event.part
        if isinstance(part, ToolReturnPart):
            tool = self._tool_by_id.pop(part.tool_call_id, None)
            if tool is not None:
                content = part.content
                await tool.show_result(content if isinstance(content, str) else str(content))

    async def _on_agent_result(self, event: AgentRunResultEvent) -> None:
        result = event.result
        if result is not None and result.response is not None:
            usage = result.response.usage
            input_token = usage.input_tokens
            output_token = usage.output_tokens
            self._context = input_token + output_token
            await self._sink.update_context(self._context)
            try:
                response_text = result.response.text
            except ValueError:
                response_text = str(result.output)
        await self._sink.finish()

    async def finish_with(self, result: AgentRunResult) -> None:
        """agent.run 路径的收尾：该路径的 handler 收不到 AgentRunResultEvent，
        由持有返回值的调用方直接喂给它。"""
        await self._on_agent_result(AgentRunResultEvent(result=result))
