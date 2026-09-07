from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic_ai import ModelMessage, RunContext
from pydantic_ai_harness import SummarizingCompaction
from pydantic_ai_harness.compaction._shared import (
    estimate_token_count,
    find_safe_cutoff,
    find_token_cutoff,
)

OnCompaction = Callable[[int, int, int], Awaitable[None]]
"""压缩完成回调：(被折进摘要的消息条数, 压缩前估算 tokens, 压缩后估算 tokens)。"""


@dataclass
class NotifyingCompaction(SummarizingCompaction):
    on_compaction: OnCompaction | None = None

    async def compact(self, messages: list[ModelMessage], ctx: RunContext) -> list[ModelMessage]:
        before = estimate_token_count(messages, self.tokenizer)
        result = await super().compact(messages, ctx)
        # 触发后仍可能空转（保留尾把 cutoff 顶回 0），历史真变了才通知
        if self.on_compaction is not None and result != messages:
            # 条数取"被总结条数"（cutoff 之前的消息数），与 harness 回执的语义一致；
            # 不是 len 差值——摘要/首条保留会抵消掉几条，净减少对人不直观
            if self.keep_tokens is not None:
                summarized = find_token_cutoff(messages, self.keep_tokens, self.tokenizer)
            else:
                summarized = find_safe_cutoff(messages, self.keep_messages)
            after = estimate_token_count(result, self.tokenizer)
            await self.on_compaction(summarized, before, after)
        return result
