from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.models import Model
from pydantic_ai_harness.experimental.acp import run_acp_stdio_sync
from starlette.applications import Starlette

from spring_harness.core.agent.agent import cap_agent
from spring_harness.core.config.model import get_model, setting
from spring_harness.core.config.settings import config
from spring_harness.core.services.model_service import resolve_model


class WEB:
    def __init__(self) -> None:
        ...
    def _resolve_models(self,model_list:list[str])->list[Model]:
        return [resolve_model(model_id) for model_id in model_list]
    def run_web_server(self)->Starlette:
        return cap_agent.to_web(models=self._resolve_models(setting.list_models()))

web = WEB()
run_web_server = web.run_web_server
