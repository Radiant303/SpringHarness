from collections.abc import AsyncIterable, Awaitable, Callable
from typing import Any

from pydantic_ai import (
    AgentRunResultEvent,
    AgentStreamEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    RunContext,
)

from spring_harness.console.sink import RenderSink


class EventStreamRenderer:
    def __init__(self, sink: RenderSink) -> None:
        self._sink = sink
        self._dispatch:dict[type, Callable[[Any], Awaitable[None]]] = {
            PartStartEvent:self._on_part_start,
            PartDeltaEvent:self._on_part_delta,
            PartEndEvent:self._on_part_end,
            AgentRunResultEvent:self._on_agent_result
        }
        self._tool_calls: dict[int, dict[str, str]] = {}


    async def __call__(self, ctx:RunContext, events:AsyncIterable[AgentStreamEvent | AgentRunResultEvent]) -> None:
        async for event in events:
            handler = self._dispatch.get(type(event))
            if handler is not None:
                await handler(event)

    async def _on_part_start(self,  event: PartStartEvent) -> None:
        ...
    async def _on_part_delta(self, event: PartDeltaEvent) -> None:
        ...

    async def _on_part_end(self, event: PartEndEvent) -> None:
        ...

    async def _on_agent_result(self, event: AgentRunResultEvent) -> None:
        await self._sink.finish()
