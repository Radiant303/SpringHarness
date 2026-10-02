"""MQ 控制面消费者（阶段④）：turn 派发/取消消费，生命周期事件回传。

拓扑与网关 RabbitConfig 一致：direct 交换机 harness.turn，队列
turn.dispatch（本网关派发）、turn.cancel（取消）、turn.lifecycle（完成回传）。
两侧重复声明均幂等；消费端 manual ack，派发按 turnId 幂等去重。

消费者与引擎同进程同事件循环运行（FastAPI lifespan 内启动），因此可以直接
通过 CloudAppServer 的进程内注册表找到会话并驱动 run_turn；token 流仍由
该会话既有的事件泵经 WS 推回（阶段⑤才切 Redis Stream）。

也可独立运行（调试 MQ 链路用）：python -m spring_harness.cloud.mq
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import TYPE_CHECKING, Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from spring_harness.core.log import logger
from spring_harness.core.rpc.connection import JsonRpcError

if TYPE_CHECKING:
    from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractRobustConnection

TURN_EXCHANGE = "harness.turn"
QUEUE_DISPATCH = "turn.dispatch"
QUEUE_CANCEL = "turn.cancel"
QUEUE_LIFECYCLE = "turn.lifecycle"
QUEUES = (QUEUE_DISPATCH, QUEUE_CANCEL, QUEUE_LIFECYCLE)

# turnId 幂等表容量：超出后淘汰最旧的一半（进程内去重，重启后的重投靠消费端快速失败兜底）
_SEEN_CAPACITY = 10_000


class TurnDispatcher:
    """turn 派发器：消费 MQ 指令驱动会话，回传生命周期事件。"""

    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: AbstractRobustConnection | None = None
        self._exchange: AbstractExchange | None = None
        self._seen: set[Any] = set()
        self._seen_order: deque[Any] = deque()

    async def start(self) -> None:
        connection: AbstractRobustConnection = await aio_pika.connect_robust(self._url)
        channel: AbstractChannel = await connection.channel(publisher_confirms=True)
        # prefetch=1：一条处理完再取下一条，同会话串行之外也不让单进程积压未确认消息
        await channel.set_qos(prefetch_count=1)
        exchange = await channel.declare_exchange(
            TURN_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True,
        )
        for name in QUEUES:
            queue = await channel.declare_queue(name, durable=True)
            await queue.bind(exchange, routing_key=name)

        dispatch_queue = await channel.declare_queue(QUEUE_DISPATCH, durable=True)
        cancel_queue = await channel.declare_queue(QUEUE_CANCEL, durable=True)
        await dispatch_queue.consume(self._on_dispatch)
        await cancel_queue.consume(self._on_cancel)

        self._connection = connection
        self._exchange = exchange
        logger.info("MQ 控制面已连接: {} (消费 {} / {})", self._url, QUEUE_DISPATCH, QUEUE_CANCEL)

    async def stop(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._exchange = None

    # ---- 消费：turn 派发/取消 ----

    async def _on_dispatch(self, message: AbstractIncomingMessage) -> None:
        # requeue=False：解析失败/派发失败的消息不重回队列（无 DLQ，直接丢弃并记日志）
        async with message.process(requeue=False):
            payload = json.loads(message.body.decode())
            turn_id = payload.get("turnId")
            session_id = payload.get("sessionId")
            text = payload.get("input", "")
            logger.info("收到 turn 派发: turnId={} sessionId={}", turn_id, session_id)

            if not self._mark_seen(turn_id):
                logger.warning("重复派发，幂等跳过: turnId={}", turn_id)
                return

            from spring_harness.cloud.ws import CloudAppServer  # 延迟导入避免循环依赖

            server = CloudAppServer._active_owners.get(session_id)
            if server is None:
                await self.publish_lifecycle({
                    "turnId": turn_id, "sessionId": session_id,
                    "status": "error", "error": "会话未挂载（客户端未连接）",
                })
                return
            try:
                server.start_turn_from_mq(session_id, text)
            except JsonRpcError as e:
                await self.publish_lifecycle({
                    "turnId": turn_id, "sessionId": session_id,
                    "status": "error", "error": e.message,
                })

    async def _on_cancel(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False):
            payload = json.loads(message.body.decode())
            session_id = payload.get("sessionId")
            logger.info("收到 turn 取消: sessionId={}", session_id)

            from spring_harness.cloud.ws import CloudAppServer  # 延迟导入避免循环依赖

            server = CloudAppServer._active_owners.get(session_id)
            if server is None:
                return  # 会话不在线：没有可取消的运行
            try:
                server.cancel_turn_from_mq(session_id)
            except JsonRpcError:
                pass  # 会话已注销：视为已取消

    # ---- 发布：生命周期事件 ----

    async def publish_lifecycle(self, payload: dict) -> None:
        if self._exchange is None:
            return
        await self._exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=QUEUE_LIFECYCLE,
        )

    # ---- turnId 幂等 ----

    def _mark_seen(self, turn_id: Any) -> bool:
        """首次见到返回 True；重复返回 False。容量超限时淘汰最旧的一半。"""
        if turn_id in self._seen:
            return False
        self._seen.add(turn_id)
        self._seen_order.append(turn_id)
        if len(self._seen_order) > _SEEN_CAPACITY:
            for _ in range(_SEEN_CAPACITY // 2):
                self._seen.discard(self._seen_order.popleft())
        return True


# ---- 进程内单例：ws.py 的 CloudAppServer 通过它回传生命周期事件 ----

_dispatcher: TurnDispatcher | None = None


def set_dispatcher(dispatcher: TurnDispatcher | None) -> None:
    global _dispatcher
    _dispatcher = dispatcher


def get_dispatcher() -> TurnDispatcher | None:
    return _dispatcher


async def _main() -> None:
    """独立运行入口：只起消费者，便于脱离引擎调试 MQ 链路。"""
    from spring_harness.core.config.settings import config

    dispatcher = TurnDispatcher(config.cloud.rabbitmq_url)
    await dispatcher.start()
    try:
        await asyncio.Event().wait()
    finally:
        await dispatcher.stop()


if __name__ == "__main__":
    asyncio.run(_main())
