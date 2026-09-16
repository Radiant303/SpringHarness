import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from spring_harness.core.stream.events import (
    BackgroundTaskFinished,
    BackgroundTaskStarted,
    ServerEvent,
)


@dataclass
class BackgroundResult:
    """一个已结束后台任务的结果，等待注入下一次模型请求。"""

    task_id: str
    tool_name: str
    args: dict[str, Any]
    output: str
    is_error: bool = False
    cancelled: bool = False


@dataclass
class _RunningTask:
    """仍在运行的后台任务记录。"""

    task_id: str
    tool_name: str
    args: dict[str, Any]
    task: asyncio.Task[Any]
    started_at: float = field(default_factory=time.monotonic)


class BackgroundTaskManager:
    """后台任务管理器：调度、收尸、暂存结果，等待 hook 取走注入上下文。

    on_event 由会话层赋值为事件队列的 put_nowait（同步回调，
    done_callback 在事件循环内触发，直接调用是安全的）。
    """

    def __init__(self, on_event: Callable[[ServerEvent], None] | None = None) -> None:
        self.on_event = on_event
        self._running: dict[str, _RunningTask] = {}
        self._finished: list[BackgroundResult] = []

    def start(
        self,
        tool_name: str,
        args: dict[str, Any],
        coro: Coroutine[Any, Any, Any],
    ) -> str:
        """把协程丢进后台执行，立即返回 task_id。"""
        task_id = uuid4().hex[:8]
        task = asyncio.create_task(coro)
        self._running[task_id] = _RunningTask(
            task_id=task_id, tool_name=tool_name, args=args, task=task,
        )
        task.add_done_callback(lambda done: self._on_done(task_id, done))
        self._notify(BackgroundTaskStarted(task_id=task_id, tool_name=tool_name, args=args))
        return task_id

    def drain_finished(self) -> list[BackgroundResult]:
        """取走全部已结束结果（取走后不再重复注入）。"""
        results, self._finished = self._finished, []
        return results

    @property
    def has_undelivered(self) -> bool:
        """还有已结束但未被 hook 取走的结果。"""
        return bool(self._finished)

    def cancel(self, task_id: str) -> bool:
        """取消一个仍在运行的任务；不存在或已结束返回 False。"""
        record = self._running.get(task_id)
        if record is None:
            return False
        record.task.cancel()
        return True

    def cancel_all(self) -> None:
        """取消全部运行中的任务（会话关闭时调用）。"""
        for record in self._running.values():
            record.task.cancel()

    def list_tasks(self) -> list[dict[str, Any]]:
        """运行中任务清单（供 list_background_tasks 工具回执）。"""
        return [
            {
                "task_id": record.task_id,
                "tool_name": record.tool_name,
                "args": record.args,
                "elapsed_seconds": round(time.monotonic() - record.started_at, 1),
            }
            for record in self._running.values()
        ]

    def _on_done(self, task_id: str, task: asyncio.Task[Any]) -> None:
        record = self._running.pop(task_id, None)
        if record is None:
            return
        cancelled = task.cancelled()
        is_error = False
        if cancelled:
            output = "任务已取消"
        else:
            try:
                value = task.result()
                output = value if isinstance(value, str) else str(value)
            except Exception as e:  # noqa: BLE001 后台任务无人值守，异常只能落成结果带回给模型
                is_error = True
                output = f"{type(e).__name__}: {e}"
        result = BackgroundResult(
            task_id=task_id, tool_name=record.tool_name, args=record.args,
            output=output, is_error=is_error, cancelled=cancelled,
        )
        self._finished.append(result)
        self._notify(BackgroundTaskFinished(
            task_id=task_id, tool_name=record.tool_name,
            result=output, is_error=is_error, cancelled=cancelled,
        ))

    def _notify(self, event: ServerEvent) -> None:
        if self.on_event is not None:
            self.on_event(event)
