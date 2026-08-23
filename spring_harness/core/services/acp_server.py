from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.models import Model
from pydantic_ai_harness.experimental.acp import run_acp_stdio_sync

from spring_harness.core.agent.agent import cap_agent
from spring_harness.core.config.model import get_model, setting
from spring_harness.core.config.settings import config


class ACP:
    def __init__(self) -> None:
        self.config = config
        self.get_model = get_model
    def resolve_acp_model(self, model_id: str) -> Model:
        """将 ACP 的模型 ID解析为 Pydantic AI Model。"""
        if model_id not in self.config._models:
            raise ValueError(f"未知的 ACP 模型: {model_id}")

        return self.get_model(model_id)

    def run_acp_server(self, agent:Agent[object, DeferredToolRequests | str],version:str="0.1.0",name:str | None="spring-harness",) -> None:
        """启动ACP服务"""
        return run_acp_stdio_sync(
            agent,
            name=name,
            version=version,
            models=setting.list_models(),
            model_resolver=self.resolve_acp_model
        )

acp = ACP()
run_acp_server = acp.run_acp_server
