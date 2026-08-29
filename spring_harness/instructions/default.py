from pydantic_ai import Agent, DeferredToolRequests, RunContext

from spring_harness.core.agent.deps import CodingAgentDeps


def register_default_instructions(
    agent: Agent[CodingAgentDeps, DeferredToolRequests | str]
):
    @agent.instructions
    async def set_workspace(ctx: RunContext[CodingAgentDeps]) -> str:
        return f"Your working directory is {ctx.deps.workspace}; you must only read, write, and operate on files within this directory and cannot access anything outside it."
