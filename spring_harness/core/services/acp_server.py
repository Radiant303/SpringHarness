from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai_harness.experimental.acp import run_acp_stdio_sync

from spring_harness.core.config.model import setting
from spring_harness.core.services.model_service import resolve_model


class ACP:
    def __init__(self) -> None:
        ...
    def run_acp_server(self, agent:Agent[object, DeferredToolRequests | str],version:str="0.1.0",name:str | None="spring-harness",) -> None:
        """启动ACP服务"""
        return run_acp_stdio_sync(
            agent,
            name=name,
            version=version,
            models=setting.list_models(),
            model_resolver=resolve_model
        )

acp = ACP()
run_acp_server = acp.run_acp_server
