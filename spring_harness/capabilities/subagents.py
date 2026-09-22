from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai_harness.subagents import SubAgent, SubAgents

from spring_harness.capabilities.research import researcher
from spring_harness.core.agent.deps import CodingAgentDeps
from spring_harness.core.config.model import get_model
from spring_harness.core.config.settings import SubAgentConfig, config
from spring_harness.toolsets.filesystem import filesystem


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



def reviewer(root_dir: str) -> SubAgent[CodingAgentDeps]:
    """代码审查子代理：只读文件访问（read_file / list_directory / search_files / find_files / file_info）。"""
    return SubAgent[CodingAgentDeps](
        agent=Agent(
            _resolve_model('reviewer'),
            name='reviewer',
            description='代码审查Agent，拥有项目文件的只读访问权限，擅长发现 bug、边界遗漏、风格不一致和潜在风险',
            instructions='你是一个代码审查子代理Agent,你的审查对象是大模型产出的代码，你的读者也是大模型。'
            '审查时先读相关文件再下结论，每条意见给出文件与位置、问题原因、修改建议；只读，不要尝试修改任何文件',
            deps_type=CodingAgentDeps,
            capabilities=[],
            toolsets=[filesystem(root_dir, read_only=True)],
        ),
        timeout_seconds=3600,
        max_calls=3,
    )


def subagents(root_dir: str) -> SubAgents[CodingAgentDeps]:
    return SubAgents[CodingAgentDeps](agents=[searcher(), reviewer(root_dir)])
