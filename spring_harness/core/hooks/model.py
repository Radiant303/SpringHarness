import asyncio
from typing import Any

from pydantic_ai import AgentRunResult, ModelRequest, ModelRequestContext, RunContext
from pydantic_ai.capabilities import Hooks

from spring_harness.core.agent.deps import CodingAgentDeps

hooks = Hooks()

@hooks.on.after_run
async def start_monitor(
    ctx: RunContext[CodingAgentDeps],
    *,
    result: AgentRunResult[Any],
) -> AgentRunResult[Any]:
    await asyncio.to_thread(ctx.deps.monitor.start)
    return result


@hooks.on.before_model_request
async def stop_monitor(
    ctx: RunContext[CodingAgentDeps],
    request_context: ModelRequestContext
) -> ModelRequestContext:
    ctx.deps.last_messages = list(request_context.messages)

    changes = await asyncio.to_thread(ctx.deps.monitor.stop)
    changes_text = ctx.deps.monitor.changes_to_string(changes)
    if changes_text is not None:
        request_context.messages.append(ModelRequest.user_text_prompt(changes_text))
    return request_context
