from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from spring_harness.cloud.api import router as api_router
from spring_harness.cloud.ws import ws_endpoint
from spring_harness.core.services.web_server import DEFAULT_FRONTEND_DIR


def create_app() -> FastAPI:
    app = FastAPI(title="spring-harness cloud", version="0.1.0")
    app.include_router(api_router)
    app.add_api_websocket_route("/ws", ws_endpoint)
    app.mount("/static", StaticFiles(directory=DEFAULT_FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(DEFAULT_FRONTEND_DIR / "index.html")

    return app
