from spring_harness.console.sink import RenderSink
from pydantic_ai.agent import

from pydantic_ai import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    PartEndEvent,
    TextPartDelta,
    ThinkingPartDelta,
    ToolCallPartDelta,
)


class EventStreamRenderer:
    def __init__(self, sink: RenderSink) -> None:
        self._sink = sink
        self._dispatch = {
            PartStartEvent:self._on_part_start
            
        }


    async def __call__(self, ctx, events) -> None:
        async for event in events:
            handler = self._dispatch[type(event)]
            await handler(self, event)

    def _on_part_start(self):
        ...
    
