from os import PathLike
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai_harness import Shell

from spring_harness.capabilities.code_mode import code_mode
from spring_harness.capabilities.planning import OnPlanChange, planning
from spring_harness.capabilities.repo_context import repo_context
from spring_harness.capabilities.skills import skills
from spring_harness.core.agent.deps import CodingAgentDeps
from spring_harness.core.config.model import get_model
from spring_harness.core.hooks.model import hooks
from spring_harness.instructions.default import register_default_instructions
from spring_harness.toolsets.filesystem import filesystem
from spring_harness.toolsets.repo_knowledge import approval_required_knowledge_toolsets


def create_agent(
    root_dir: str | PathLike[str] | Path = ".",
    model_name: str | None = None,
    session_id: str = "default",
    plan_on_change: OnPlanChange | None = None,
) -> Agent[CodingAgentDeps, DeferredToolRequests | str]:
    """
    创建 Spring Harness Agent
    """
    root = Path(root_dir).expanduser().resolve()

    agent = Agent(
        model=get_model(model_name),
        toolsets=[
            filesystem(str(root)),
            approval_required_knowledge_toolsets
        ],
        output_type=[
            str,
            DeferredToolRequests,
        ],
        deps_type=CodingAgentDeps,
        capabilities=[
            hooks,
            skills(),
            planning(session_id, on_change=plan_on_change),
            repo_context(root),
            code_mode(root),
            Shell()
        ],
    )

    register_default_instructions(agent)

    return agent
