from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from spring_harness.cloud.mq import TurnDispatcher, set_dispatcher
from spring_harness.cloud.registry import CloudSessionRegistry, set_registry
from spring_harness.cloud.ws import ws_endpoint
from spring_harness.core.config.settings import config
from spring_harness.core.log import logger
from spring_harness.core.services.web_server import DEFAULT_FRONTEND_DIR


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # 阶段⑤：进程级会话注册表 + Redis Stream 事件流（断线续传的前提）
    redis_client = aioredis.from_url(config.cloud.redis_url, decode_responses=True)
    registry = CloudSessionRegistry(redis_client)
    set_registry(registry)

    # 阶段④：MQ 控制面。MQ 不可用时网关发布会失败并回退 WS 透传
    # （turn/start 走引擎 RPC），本进程则仅缺席生命周期回传
    dispatcher = TurnDispatcher(config.cloud.rabbitmq_url)
    try:
        await dispatcher.start()
    except Exception:
        logger.exception("MQ 控制面连接失败，turn 派发不可用（可回退 WS 透传）")
        set_dispatcher(None)
    else:
        set_dispatcher(dispatcher)
    try:
        yield
    finally:
        set_dispatcher(None)
        await dispatcher.stop()
        set_registry(None)
        await registry.close_all()
        await redis_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="spring-harness cloud", version="0.1.0", lifespan=lifespan)
    app.add_api_websocket_route("/ws", ws_endpoint)
    app.mount("/static", StaticFiles(directory=DEFAULT_FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(DEFAULT_FRONTEND_DIR / "index.html")

    return app
