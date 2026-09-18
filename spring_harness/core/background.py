import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from spring_harness.core.log import logger
from spring_harness.core.stream.events import (
    BackgroundTaskFinished,
    BackgroundTaskStarted,
    ServerEvent,
)

_SHUTDOWN_TIMEOUT = 5.0


@dataclass
class BackgroundResult:
    """一个已结束后台任务的结果。
    """

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


def format_notice(results: list[BackgroundResult]) -> str:
    """后台任务结束通知：唯一文案，忙碌注入与空闲催醒两条路径共用。

    只带通知说法 + task_id + 状态，不含结果内容——内容让模型用 job_output 自取。
    """
    lines = []
    for result in results:
        status = "已取消" if result.cancelled else ("出错" if result.is_error else "已完成")
        lines.append(f"- 任务 {result.task_id}（{result.tool_name}）：{status}")
    return (
        "（系统通知：以下后台任务已结束。结果内容不在此展示，"
        "请用 job_output 工具传入 task_id 获取）\n"
        + "\n".join(lines)
        + "\n"
    )


class BackgroundTaskManager:
    """后台任务管理器：调度、收尸、结果存内存 Map、通知排队等待投递。

    on_event 由会话层赋值为事件队列的 put_nowait（同步回调，
    done_callback 在事件循环内触发，直接调用是安全的）。
    """

    def __init__(self, on_event: Callable[[ServerEvent], None] | None = None) -> None:
        self.on_event = on_event
        self._running: dict[str, _RunningTask] = {}
        self._results: dict[str, BackgroundResult] = {}
        self._pending: list[BackgroundResult] = []

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

    # ---- 结果 Map：job_output 的查询源，会话存活期保留 ----

    def get_result(self, task_id: str) -> BackgroundResult | None:
        """已结束任务的结果"""
        return self._results.get(task_id)

    def running_info(self, task_id: str) -> dict[str, Any] | None:
        """运行中任务的简报"""
        record = self._running.get(task_id)
        if record is None:
            return None
        return {
            "task_id": record.task_id,
            "tool_name": record.tool_name,
            "args": record.args,
            "elapsed_seconds": round(time.monotonic() - record.started_at, 1),
        }

    # ---- 待通知队列：hook 在模型请求前消费，空闲时触发催醒轮 ----

    def peek_pending(self) -> list[BackgroundResult]:
        """非破坏性地看待通知结果（催醒轮发展示事件用；真正消费走 drain_pending）。"""
        return list(self._pending)

    def drain_pending(self) -> list[BackgroundResult]:
        """取走全部待通知结果。"""
        results, self._pending = self._pending, []
        return results

    @property
    def has_pending(self) -> bool:
        """还有已结束但通知未投递的任务。"""
        return bool(self._pending)

    # ---- 取消与关闭 ----

    def cancel(self, task_id: str) -> bool:
        """取消一个仍在运行的任务"""
        record = self._running.get(task_id)
        if record is None:
            return False
        record.task.cancel()
        return True

    async def shutdown(self, timeout: float = _SHUTDOWN_TIMEOUT) -> None:
        """取消全部运行中任务并等待收尸"""
        tasks = [record.task for record in self._running.values()]
        for task in tasks:
            task.cancel()
        if not tasks:
            return
        _done, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in pending:
            logger.warning("后台任务关闭超时，放弃收尸: {}", task.get_name())

    def list_running(self) -> list[dict[str, Any]]:
        """运行中任务清单"""
        return [
            info
            for task_id in self._running
            if (info := self.running_info(task_id)) is not None
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
        self._results[task_id] = result
        self._pending.append(result)
        self._notify(BackgroundTaskFinished(
            task_id=task_id, tool_name=record.tool_name,
            is_error=is_error, cancelled=cancelled,
        ))

    def _notify(self, event: ServerEvent) -> None:
        if self.on_event is not None:
            self.on_event(event)
