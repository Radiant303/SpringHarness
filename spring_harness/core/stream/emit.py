import asyncio
from collections.abc import Awaitable, Callable
from uuid import uuid4

from pydantic_ai import ToolCallPart

from spring_harness.core.stream.events import (
    ApprovalRequest,
    QuestionRequest,
    ServerEvent,
    TextDelta,
    ThinkingDelta,
    ToolArgsDelta,
    ToolCallStarted,
    ToolDiff,
    ToolFinished,
    ToolPending,
    TurnFinished,
    UsageUpdated,
)
from spring_harness.core.stream.sink import ToolCallSink
from spring_harness.utils.diff import make_diff


class EventEmitter:
    def __init__(self, emit: Callable[[ServerEvent], Awaitable[None]]) -> None:
        self._emit = emit

    async def write_thinking(self, text: str) -> None:
        await self._emit(ThinkingDelta(text=text))

    async def write_answer(self, text: str) -> None:
        await self._emit(TextDelta(text=text))

    async def start_tool_call(self, name: str, tool_call_id: str) -> ToolCallSink:
        await self._emit(ToolCallStarted(tool_call_id=tool_call_id, tool_name=name))
        return _ToolCallEmitter(self._emit, tool_call_id)

    async def finish(self) -> None:
        await self._emit(TurnFinished())

    async def update_context(self, tokens: int) -> None:
        await self._emit(UsageUpdated(context_tokens=tokens))


class _ToolCallEmitter:
    def __init__(self, emit, tool_call_id: str) -> None:
        self._emit = emit
        self._id = tool_call_id

    async def write_args(self, chunk: str) -> None:
        await self._emit(ToolArgsDelta(tool_call_id=self._id, args_chunk=chunk))

    async def show_result(self, result: str, is_error: bool = False) -> None:
        await self._emit(ToolFinished(tool_call_id=self._id, result=result, is_error=is_error))

    async def show_diff(self, diff: str) -> None:
        await self._emit(ToolDiff(tool_call_id=self._id, diff=diff))

    async def show_pending(self, label: str = "等待批准") -> None:
        await self._emit(ToolPending(tool_call_id=self._id, label=label))


class PendingRequests:
    def __init__(self, emit: Callable[..., Awaitable[None]]) -> None:
        self._emit = emit
        self._pending: dict[str, asyncio.Future] = {}

    async def ask(self, call: ToolCallPart) -> bool:
        request_id = uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._emit(ApprovalRequest(
            request_id=request_id, tool_call_id=call.tool_call_id,
            tool_name=call.tool_name, args=call.args_as_dict(),
            diff=make_diff(call.tool_name, call.args),
        ))
        return await future

    async def ask_question(self, args: dict) -> str | None:
        request_id = uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._emit(QuestionRequest(
            request_id=request_id,
            question=args["question"],
            options=args.get("options"),
            allow_custom=args.get("allow_custom", True),
        ))
        return await future

    def resolve(self, request_id: str, value) -> None:
        future = self._pending.pop(request_id, None)
        if future and not future.done():
            future.set_result(value)

    def cancel_all(self) -> None:
        for f in self._pending.values():
            f.cancel()
        self._pending.clear()
