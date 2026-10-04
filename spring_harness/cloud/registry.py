"""云端会话注册表（阶段⑤）：会话生命周期与 WS 连接解耦。

阶段④里会话由连接持有，浏览器断开 → 引擎侧连接关闭 → 会话被销毁、turn 被
取消。断线续传的前提是 turn 在断线后继续运行，因此会话改为进程级注册表持有：

- 每个会话一个"扇出"任务消费 HarnessSession 事件：普通事件 XADD 到
  Redis Stream（stream:session:{id}，滑动 TTL，turn 结束后缩短保留期）；
  审批/提问路由给当前挂载的连接，断线期间暂存，重新挂载时补投。
- WS 连接（CloudAppServer）只是"挂载/卸载"：挂载时成为审批路由目标，
  断开时摘除目标并默认拒绝在途审批（宁安全勿放行），会话本身不动。
- MQ 派发器经注册表驱动 turn（start_turn/cancel_turn），生命周期事件由
  扇出任务在 TurnFinished 时回传。
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from spring_harness.core.log import logger
from spring_harness.core.rpc.connection import JsonRpcError
from spring_harness.core.rpc.server import BUSY, AppServer
from spring_harness.core.session import HarnessSession
from spring_harness.core.stream.events import ApprovalRequest, QuestionRequest, TurnFinished

if TYPE_CHECKING:
    from pathlib import Path

    import redis.asyncio as aioredis

    from spring_harness.core.store.base import SessionStore
    from spring_harness.core.stream.events import ServerEvent

STREAM_KEY_PREFIX = "stream:session:"
# 滑动过期：每条事件写入都续期，活跃会话的流不会中途消失
STREAM_TTL_SECONDS = 3600
# turn 结束后缩短保留期：续传窗口已过，历史兜底在网关
STREAM_TTL_AFTER_FINISH = 600


class CloudSessionHandle:
    """一个云端会话的运行时：HarnessSession + 事件扇出 + 审批路由。"""

    def __init__(self, session: HarnessSession, redis: aioredis.Redis | None) -> None:
        self.session = session
        self._redis = redis
        self._approval_target: AppServer | None = None
        self._parked_requests: list[ApprovalRequest | QuestionRequest] = []
        self._tasks: set[asyncio.Task] = set()
        self._fanout_task = self._track(asyncio.create_task(self._fanout_loop()))

    @property
    def session_id(self) -> str:
        return self.session.session_id

    @property
    def approval_target(self) -> AppServer | None:
        return self._approval_target

    # ---- 连接挂载/卸载 ----

    def set_approval_target(self, server: AppServer | None) -> None:
        self._approval_target = server
        if server is not None and self._parked_requests:
            parked, self._parked_requests = self._parked_requests, []
            for event in parked:
                logger.info("补投断线期间暂存的审批/提问: session={} kind={}",
                            self.session_id, type(event).__name__)
                self._track(asyncio.create_task(self._route_request(event)))

    # ---- turn 驱动（MQ 派发器调用） ----

    def start_turn(self, text: str) -> None:
        if self.session.busy:
            raise JsonRpcError(BUSY, "上一轮还没结束")
        self._track(asyncio.create_task(self._run(text)))

    def cancel_turn(self) -> None:
        self.session.cancel()

    async def _run(self, text: str) -> None:
        try:
            await self.session.run_turn(text)
        except Exception:  # noqa: BLE001 run_turn 正常路径已自收口，到这属于意外
            logger.exception("会话 {} 的轮次异常", self.session_id)

    # ---- 事件扇出 ----

    def _track(self, task: asyncio.Task) -> asyncio.Task:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _fanout_loop(self) -> None:
        try:
            async for event in self.session.events():
                if isinstance(event, (ApprovalRequest, QuestionRequest)):
                    await self._route_request(event)
                else:
                    await self._write_stream(event)
                    if isinstance(event, TurnFinished):
                        await self._publish_lifecycle(event)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 扇出是长驻任务：任何意外只记日志，不让任务静默死掉
            logger.exception("会话 {} 的事件扇出异常退出", self.session_id)

    async def _route_request(self, event: ApprovalRequest | QuestionRequest) -> None:
        target = self._approval_target
        if target is None:
            self._parked_requests.append(event)
            logger.info("会话 {} 无在线连接，审批/提问暂存: {}", self.session_id, type(event).__name__)
            return
        await target.post_session_request(self.session, event)

    async def _write_stream(self, event: ServerEvent) -> None:
        if self._redis is None:
            return
        key = STREAM_KEY_PREFIX + self.session_id
        try:
            await self._redis.xadd(key, {"event": json.dumps(event.model_dump(), ensure_ascii=False)})
            ttl = STREAM_TTL_AFTER_FINISH if isinstance(event, TurnFinished) else STREAM_TTL_SECONDS
            await self._redis.expire(key, ttl)
        except Exception:  # noqa: BLE001 流写入失败不阻断 turn；事件仍经网关落库
            logger.exception("事件写 Redis Stream 失败: session={}", self.session_id)

    async def _publish_lifecycle(self, event: TurnFinished) -> None:
        from spring_harness.cloud.mq import get_dispatcher  # 延迟导入避免循环依赖

        dispatcher = get_dispatcher()
        if dispatcher is None:
            return
        if event.cancelled:
            status = "cancelled"
        elif event.error:
            status = "error"
        else:
            status = "finished"
        try:
            await dispatcher.publish_lifecycle({
                "sessionId": self.session_id,
                "status": status,
                "error": event.error,
                "wake": event.wake,
            })
        except Exception:  # noqa: BLE001 生命周期回传失败不影响事件流
            logger.exception("turn 生命周期事件发布失败: session={}", self.session_id)

    # ---- 关闭（进程退出时调用） ----

    async def close(self) -> None:
        self._fanout_task.cancel()
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.session.close()


class CloudSessionRegistry:
    """进程级会话表：session_id → CloudSessionHandle。"""

    def __init__(self, redis: aioredis.Redis | None) -> None:
        self._redis = redis
        self._handles: dict[str, CloudSessionHandle] = {}

    def get(self, session_id: str) -> CloudSessionHandle | None:
        return self._handles.get(session_id)

    async def get_or_create(
        self, session_id: str, *, workspace: Path, store: SessionStore,
    ) -> CloudSessionHandle:
        handle = self._handles.get(session_id)
        if handle is not None:
            return handle
        # 工作区目录惰性创建：sessions 行可能由网关 REST 建的（本进程还没建过目录）
        workspace.mkdir(parents=True, exist_ok=True)
        session = await asyncio.to_thread(HarnessSession, workspace, store=store)
        handle = CloudSessionHandle(session, self._redis)
        self._handles[session_id] = handle
        logger.info("云端会话已注册: {}", session_id)
        return handle

    async def close_all(self) -> None:
        handles, self._handles = list(self._handles.values()), {}
        await asyncio.gather(*(h.close() for h in handles), return_exceptions=True)


_registry: CloudSessionRegistry | None = None


def set_registry(registry: CloudSessionRegistry | None) -> None:
    global _registry
    _registry = registry


def get_registry() -> CloudSessionRegistry | None:
    return _registry
