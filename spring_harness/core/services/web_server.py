from typing import cast
from pathlib import Path

from pydantic_ai.models import Model
from starlette.applications import Starlette

from spring_harness.core.agent.agent import SpringAgent
from spring_harness.core.config.model import setting
from spring_harness.core.services.model_service import resolve_model


class SpringWEB:
    def __init__(self) -> None:
        ...
    def _resolve_models(self, model_list: list[str]) -> dict[str, Model]:
        return {
            model_id: resolve_model(model_id)
            for model_id in model_list
        }

    def run_web_server(self, root_dir: str | Path | None = None) -> Starlette:
        agent = SpringAgent(root_dir or Path.cwd()).agent
        return agent.to_web(models=self._resolve_models(setting.list_models()))


web = SpringWEB()
run_web_server = web.run_web_server
