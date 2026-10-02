"""MQ 控制面消费者（阶段④）：turn 派发/取消消费，生命周期事件回传。

拓扑与网关 RabbitConfig 一致：direct 交换机 harness.turn，队列
turn.dispatch（网关派发）、turn.cancel（取消）、turn.lifecycle（完成回传），
各自挂死信交换机 harness.turn.dlx（同名 .dlq 队列）。
两侧重复声明的参数必须完全一致，否则 RabbitMQ 报 406 PRECONDITION_FAILED。

可靠性：manual ack；消费失败按 x-death 计数有限重投（≤3 次），超限进 DLQ；
派发按 turnId 幂等去重。

消费者与引擎同进程同事件循环运行（FastAPI lifespan 内启动），经进程级会话
注册表（cloud.registry）驱动 turn；token 流经 Redis Stream（阶段⑤）。

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
TURN_DLX = "harness.turn.dlx"
QUEUE_DISPATCH = "turn.dispatch"
QUEUE_CANCEL = "turn.cancel"
QUEUE_LIFECYCLE = "turn.lifecycle"
QUEUES = (QUEUE_DISPATCH, QUEUE_CANCEL, QUEUE_LIFECYCLE)

# 消费失败重投上限：重投次数记在消息头 x-retry-count（requeue 不累计数，只能复制重发），超限进 DLQ
MAX_REQUEUE = 3
RETRY_HEADER = "x-retry-count"

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
        dlx = await channel.declare_exchange(
            TURN_DLX, aio_pika.ExchangeType.DIRECT, durable=True,
        )
        queues = {}
        for name in QUEUES:
            queue = await channel.declare_queue(
                name, durable=True,
                # 与网关 RabbitConfig.businessQueue 保持一致
                arguments={
                    "x-dead-letter-exchange": TURN_DLX,
                    "x-dead-letter-routing-key": f"{name}.dlq",
                },
            )
            await queue.bind(exchange, routing_key=name)
            dlq = await channel.declare_queue(f"{name}.dlq", durable=True)
            await dlq.bind(dlx, routing_key=f"{name}.dlq")
            queues[name] = queue

        self._connection = connection
        self._exchange = exchange

        await queues[QUEUE_DISPATCH].consume(self._on_dispatch)
        await queues[QUEUE_CANCEL].consume(self._on_cancel)
        logger.info("MQ 控制面已连接: {} (消费 {} / {})", self._url, QUEUE_DISPATCH, QUEUE_CANCEL)

    async def stop(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._exchange = None

    # ---- 消费：turn 派发/取消 ----

    async def _on_dispatch(self, message: AbstractIncomingMessage) -> None:
        try:
            payload = json.loads(message.body.decode())
            turn_id = payload.get("turnId")
            session_id = payload.get("sessionId")
            text = payload.get("input", "")
            logger.info("收到 turn 派发: turnId={} sessionId={}", turn_id, session_id)

            if not self._mark_seen(turn_id):
                logger.warning("重复派发，幂等跳过: turnId={}", turn_id)
                await message.ack()
                return

            from spring_harness.cloud.registry import get_registry

            registry = get_registry()
            handle = registry.get(session_id) if registry is not None else None
            if handle is None:
                await self.publish_lifecycle({
                    "turnId": turn_id, "sessionId": session_id,
                    "status": "error", "error": "会话未挂载（客户端未连接）",
                })
            else:
                try:
                    handle.start_turn(text)
                except JsonRpcError as e:
                    await self.publish_lifecycle({
                        "turnId": turn_id, "sessionId": session_id,
                        "status": "error", "error": e.message,
                    })
        except Exception:
            # 意外失败（如消息体损坏）：有限重投，超限进 DLQ
            logger.exception("turn 派发处理失败")
            await self._nack_with_retry(message)
            return
        await message.ack()

    async def _on_cancel(self, message: AbstractIncomingMessage) -> None:
        try:
            payload = json.loads(message.body.decode())
            session_id = payload.get("sessionId")
            logger.info("收到 turn 取消: sessionId={}", session_id)

            from spring_harness.cloud.registry import get_registry

            registry = get_registry()
            handle = registry.get(session_id) if registry is not None else None
            if handle is not None:
                handle.cancel_turn()
        except Exception:
            logger.exception("turn 取消处理失败")
            await self._nack_with_retry(message)
            return
        await message.ack()

    async def _nack_with_retry(self, message: AbstractIncomingMessage) -> None:
        """有限重投：requeue 不会累加任何计数（x-death 只在死信转投时记录），
        所以重投次数记在自定义头 x-retry-count——失败时把消息复制一份（计数 +1）
        发回原队列并 ack 原件；超限后 nack(requeue=False) 进 DLQ 由网关告警。"""
        retries = (message.headers or {}).get(RETRY_HEADER) or 0
        if retries < MAX_REQUEUE and self._exchange is not None:
            await self._exchange.publish(
                aio_pika.Message(
                    body=message.body,
                    content_type=message.content_type,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    headers={**(message.headers or {}), RETRY_HEADER: retries + 1},
                ),
                routing_key=message.routing_key,
            )
            await message.ack()
            logger.warning("消息处理失败，重投（第 {} 次）", retries + 1)
        else:
            await message.nack(requeue=False)
            logger.error("消息重投 {} 次仍失败，进入 DLQ", retries)

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
