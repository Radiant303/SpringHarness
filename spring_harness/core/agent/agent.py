# spring_harness/core/agent.py

from os import PathLike
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai_harness import Skills

from spring_harness.capabilities.filesystem import filesystem
from spring_harness.core.agent.deps import CodingAgentDeps
from spring_harness.core.config.model import get_model
from spring_harness.core.hooks.model import hooks
from spring_harness.instructions.default import register_default_instructions


def create_agent(
    root_dir: str | PathLike[str] | Path = ".",
) -> Agent[CodingAgentDeps, DeferredToolRequests | str]:
    """
    创建 Spring Harness Agent
    """
    root = Path(root_dir).expanduser().resolve()

    agent = Agent(
        model=get_model(),
        toolsets=[
            filesystem(str(root)),
        ],
        output_type=[
            str,
            DeferredToolRequests,
        ],
        deps_type=CodingAgentDeps,
        capabilities=[hooks,Skills(Path.home() / ".springharness" / "skills")],
    )

    register_default_instructions(agent)

    return agent
