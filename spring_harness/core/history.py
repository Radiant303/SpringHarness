from dataclasses import dataclass
from typing import Literal

from pydantic_ai import ModelMessage

HistoryDirection = Literal["forward", "backward"]


@dataclass
class HistoryPage:
    segments: list[list[ModelMessage]]
    first_segment_index: int | None = None
    next_cursor: str | None = None
    previous_cursor: str | None = None
    has_more: bool = False
