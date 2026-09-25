from typing import Protocol

from pydantic_ai import ModelMessage

from spring_harness.core.history import HistoryDirection, HistoryPage


class SessionStore(Protocol):
    """会话消息存储：一个会话一个 store 对象。

    追加原则：只增不改；历史被压缩/合并改写时追加新段，旧段保留备查。
    本地实现见 jsonl.py（每会话一个 JSONL 文件），云端实现见 mysql.py。
    """

    @property
    def session_id(self) -> str: ...

    def append(self, messages: list[ModelMessage]) -> None:
        """每轮结束（含异常终止）后调用，追加增量。"""
        ...

    def append_rewritten(self, messages: list[ModelMessage]) -> None:
        """历史被压缩/改写时调用：开新段写入新基线，旧段保留。"""
        ...

    def query_history(
        self,
        cursor: str | None = None,
        limit: int | None = None,
        direction: HistoryDirection = "forward",
    ) -> tuple[list[ModelMessage], HistoryPage]:
        """返回（发给模型的当前历史, 分页历史快照）。

        游标钉住存储快照，后续追加和改写不影响既有分页；新查询用空游标。
        limit=None 返回完整当前历史，此时不接受 cursor。
        """
        ...
