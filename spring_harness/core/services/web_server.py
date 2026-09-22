from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from spring_harness.core.config.settings import config
from spring_harness.core.log import logger
from spring_harness.core.rpc.connection import JsonRpcConnection
from spring_harness.core.rpc.schema import InitializeResult
from spring_harness.core.rpc.server import PROTOCOL_VERSION, AppServer

DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"


class _WireModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ModelInfo(_WireModel):
    id: str
    display_name: str = Field(validation_alias="displayName", serialization_alias="displayName")
    provider: str
    max_context_size: int = Field(validation_alias="maxContextSize", serialization_alias="maxContextSize")


class ModelsListResult(_WireModel):
    models: list[ModelInfo]
    default_model: str = Field(validation_alias="defaultModel", serialization_alias="defaultModel")


class WebInitializeResult(InitializeResult):
    workspace: str
    models: list[ModelInfo]
    default_model: str = Field(validation_alias="defaultModel", serialization_alias="defaultModel")


def _model_infos() -> list[ModelInfo]:
    return [
        ModelInfo(
            id=model_id,
            display_name=model.display_name,
            provider=model.provider,
            max_context_size=model.max_context_size,
        )
        for model_id, model in config.models.items()
    ]


class WebAppServer(AppServer):
    """stdio 协议面 + Web 端引导信息（workspace / 模型列表）。"""

    def __init__(self, connection: JsonRpcConnection, workspace: Path) -> None:
        super().__init__(connection)
        self._workspace = workspace
        self._routes["models/list"] = (None, self._models_list)

    async def _initialize(self, _: None) -> WebInitializeResult:
        return WebInitializeResult(
            server_name="spring-harness",
            protocol_version=PROTOCOL_VERSION,
            workspace=str(self._workspace),
            models=_model_infos(),
            default_model=config.default_model,
        )

    async def _models_list(self, _: None) -> ModelsListResult:
        return ModelsListResult(models=_model_infos(), default_model=config.default_model)


class SpringWEB:
    def run_web_server(
        self,
        root_dir: str | Path | None = None,
        frontend_dir: str | Path | None = None,
    ) -> Starlette:
        workspace = Path(root_dir or Path.cwd()).expanduser().resolve()
        frontend = Path(frontend_dir).expanduser().resolve() if frontend_dir else DEFAULT_FRONTEND_DIR

        async def ws_endpoint(websocket: WebSocket) -> None:
            await websocket.accept()

            async def read_line() -> str | None:
                try:
                    return await websocket.receive_text()
                except (WebSocketDisconnect, RuntimeError):
                    return None  # 对端关闭 = EOF，驱动 connection.run 收尾

            async def write_line(line: str) -> None:
                try:
                    await websocket.send_text(line)
                except (WebSocketDisconnect, RuntimeError) as e:
                    try:
                        await websocket.close()
                    except (WebSocketDisconnect, RuntimeError):
                        pass
                    raise ConnectionError("WebSocket 已关闭") from e

            connection = JsonRpcConnection(read_line, write_line)
            server = WebAppServer(connection, workspace)
            logger.info("web 客户端已连接: {}", websocket.client)
            try:
                await connection.run(server.handle_request, server.handle_notification)
            finally:
                await server.shutdown()
                logger.info("web 客户端已断开: {}", websocket.client)

        async def index(_: Request) -> FileResponse:
            return FileResponse(frontend / "index.html")

        return Starlette(
            routes=[
                Route("/", index),
                WebSocketRoute("/ws", ws_endpoint),
                Mount("/static", app=StaticFiles(directory=frontend), name="static"),
            ],
        )


web = SpringWEB()
run_web_server = web.run_web_server
