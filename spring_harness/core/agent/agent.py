from os import PathLike
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai_harness import Shell

from spring_harness.capabilities.code_mode import code_mode
from spring_harness.capabilities.compaction import NotifyingCompaction, OnCompaction
from spring_harness.capabilities.planning import OnPlanChange, planning
from spring_harness.capabilities.repo_context import repo_context
from spring_harness.capabilities.skills import skills
from spring_harness.capabilities.subagents import subagents
from spring_harness.capabilities.teaching import (
    OnTeachingChange,
    teaching_store_for,
    teaching_toolset,
)
from spring_harness.core.agent import (
    shell_patch as _shell_patch,  # noqa: F401  # Windows 杀进程补丁，导入即生效
)
from spring_harness.core.agent.deps import CodingAgentDeps
from spring_harness.core.config.model import get_model, get_model_config
from spring_harness.core.config.settings import loop_control
from spring_harness.core.hooks.model import hooks
from spring_harness.instructions.default import register_default_instructions
from spring_harness.toolsets.ask_user import ask_user_toolset
from spring_harness.toolsets.filesystem import filesystem
from spring_harness.toolsets.repo_knowledge import approval_required_knowledge_toolsets


class SpringAgent(Agent[CodingAgentDeps, DeferredToolRequests | str]):
    """三个入口（CLI / ACP / Web）共用的 Agent：注入配置里的默认请求数上限。

    pydantic-ai 的 usage_limits 只能逐次 run 传入，没有 Agent 级默认值；而
    run / run_stream / run_sync 以及 to_web、ACP 适配器最终都汇入 iter()，
    在这里注入默认值即可一处生效、处处覆盖；调用方显式传入的优先。
    subagents 能力内部自建 Agent，不走这里，子代理仍是库默认 50。
    """

    def iter(self, user_prompt: Any = None, **kwargs: Any):  # type: ignore[override]
        if kwargs.get("usage_limits") is None:
            kwargs["usage_limits"] = UsageLimits(request_limit=loop_control.request_limit)
        return super().iter(user_prompt, **kwargs)


def create_agent(
    root_dir: str | PathLike[str] | Path = ".",
    model_name: str | None = None,
    session_id: str = "default",
    plan_on_change: OnPlanChange | None = None,
    teach_on_change: OnTeachingChange | None = None,
    compact_on_change: OnCompaction | None = None,
) -> SpringAgent:
    """
    创建 Spring Harness Agent
    """
    root = Path(root_dir).expanduser().resolve()
    model = get_model(model_name)
    model_config = get_model_config(model_name)
    agent = SpringAgent(
        model=model,
        toolsets=[
            filesystem(str(root)),
            approval_required_knowledge_toolsets,
            ask_user_toolset,
            teaching_toolset(teaching_store_for(root, on_change=teach_on_change)),
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
            subagents(),
            Shell(),
            NotifyingCompaction(
                max_fraction=0.8,
                keep_messages=4,
                fallback_context_window=model_config.max_context_size,
                on_compaction=compact_on_change,
            )
        ],
        retries=20
    )

    register_default_instructions(agent)

    return agent
