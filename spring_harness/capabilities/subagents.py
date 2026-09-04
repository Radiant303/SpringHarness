from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai_harness.subagents import SubAgent, SubAgents

from spring_harness.capabilities.research import researcher
from spring_harness.core.agent.deps import CodingAgentDeps
from spring_harness.core.config.model import get_model
from spring_harness.core.config.settings import SubAgentConfig, config


def _resolve_model(name: str) -> Model | None:
    """config.toml 的 [subagents.<name>] model 单独配置；留空返回 None，
    委托时继承主 agent 当前模型。"""
    model_name = config.subagents.get(name, SubAgentConfig()).model
    return get_model(model_name) if model_name else None


def searcher() -> SubAgent[CodingAgentDeps]:
    return SubAgent[CodingAgentDeps](
        agent=Agent(
            _resolve_model('searcher'),
            name='searcher',
            description='强大的搜索Agent，具有世界上最丰富的知识库',
            instructions='你是一个知识搜索子代理Agent,善于科普，你的科普对象是大模型，你需要让你的输出能够让大模型听懂即可',
            deps_type=CodingAgentDeps,
            capabilities=[researcher()],
            toolsets=[],
        ),
        timeout_seconds=360,
        max_calls=3,
    )



def subagents() -> SubAgents[CodingAgentDeps]:
    return SubAgents[CodingAgentDeps](agents=[searcher()])
