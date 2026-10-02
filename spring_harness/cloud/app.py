from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from spring_harness.cloud.api import router as api_router
from spring_harness.cloud.mq import TurnDispatcher, set_dispatcher
from spring_harness.cloud.ws import ws_endpoint
from spring_harness.core.config.settings import config
from spring_harness.core.log import logger
from spring_harness.core.services.web_server import DEFAULT_FRONTEND_DIR


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # MQ 控制面（阶段④）：turn 派发/取消消费 + 生命周期回传。
    # MQ 不可用时本网关侧发布会失败并回退 WS 透传（turn/start 走引擎 RPC），
    # 本进程则仅缺席生命周期回传，其余功能不受影响
    dispatcher = TurnDispatcher(config.cloud.rabbitmq_url)
    try:
        await dispatcher.start()
    except Exception:
        logger.exception("MQ 控制面连接失败，turn 派发降级为 WS 直推")
        set_dispatcher(None)
    else:
        set_dispatcher(dispatcher)
    try:
        yield
    finally:
        set_dispatcher(None)
        await dispatcher.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="spring-harness cloud", version="0.1.0", lifespan=lifespan)
    app.include_router(api_router)
    app.add_api_websocket_route("/ws", ws_endpoint)
    app.mount("/static", StaticFiles(directory=DEFAULT_FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(DEFAULT_FRONTEND_DIR / "index.html")

    return app
