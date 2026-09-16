from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from pydantic_ai import (
    CallDeferred,
    ModelRequest,
    ModelRequestContext,
    RunContext,
    UserPromptPart,
)
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import ApprovalRequired
from pydantic_ai.toolsets import (
    AbstractToolset,
    FunctionToolset,
    ToolsetTool,
    WrapperToolset,
)

from spring_harness.core.agent.deps import CodingAgentDeps
from spring_harness.core.background import BackgroundResult
from spring_harness.core.hooks.model import BACKGROUND_TASK_SOURCE

BACKGROUND_PREFIX = "Background_"

_BACKGROUND_NOTE = (
    "\n\n后台执行变体：调用后立即返回 task_id，任务在后台继续运行，"
    "结果完成后由系统自动注入上下文并唤醒你，届时再基于结果继续。"
    "不要轮询等待：如果需要结果才能往下走，先结束本轮回复（告诉用户任务已在后台进行）。"
    "这个 task_id 与 Shell 的 command_id 无关，不能用于 check_command/stop_command。"
)


def _is_backgroundable(name: str, tool: ToolsetTool[CodingAgentDeps], extra_tools: frozenset[str]) -> bool:
    """metadata 标记优先；extra_tools 按名字兜底（第三方能力加不了 metadata）。

    只放行 function/unapproved：external 等延迟种类在执行前就被图收走，
    call_tool 根本轮不到我们调度，生成变体只会变成没人认领的悬挂调用。
    """
    if name.startswith(BACKGROUND_PREFIX):
        return False
    if tool.tool_def.kind not in ("function", "unapproved"):
        return False
    metadata = tool.tool_def.metadata or {}
    return bool(metadata.get("backgroundable")) or name in extra_tools


@dataclass
class BackgroundableToolset(WrapperToolset[CodingAgentDeps]):
    """为标记 backgroundable 的工具生成 Background_ 前缀变体（仿 RenamedToolset 的 replace 改名法）。

    变体只改 name/description，tool_def.kind 原样保留：声明式审批（requires_approval）
    随之继承，图会把 Background_ 调用本身转入延迟审批，批准后 call_tool 才真正调度。
    """

    extra_tools: frozenset[str] = frozenset()

    async def get_tools(self, ctx: RunContext[CodingAgentDeps]) -> dict[str, ToolsetTool[CodingAgentDeps]]:
        tools = await super().get_tools(ctx)
        for name, tool in list(tools.items()):
            if not _is_backgroundable(name, tool, self.extra_tools):
                continue
            variant_name = BACKGROUND_PREFIX + name
            if variant_name in tools:
                continue
            tools[variant_name] = replace(
                tool,
                toolset=self,
                tool_def=replace(
                    tool.tool_def,
                    name=variant_name,
                    description=(tool.tool_def.description or "") + _BACKGROUND_NOTE,
                ),
            )
        return tools

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[CodingAgentDeps],
        tool: ToolsetTool[CodingAgentDeps],
    ) -> Any:
        if not name.startswith(BACKGROUND_PREFIX):
            return await super().call_tool(name, tool_args, ctx, tool)
        original_name = name[len(BACKGROUND_PREFIX):]
        run_ctx = replace(ctx, tool_name=original_name)
        original_tool = replace(tool, tool_def=replace(tool.tool_def, name=original_name))

        async def run() -> str:
            try:
                value = await self.wrapped.call_tool(original_name, tool_args, run_ctx, original_tool)
            except ApprovalRequired:
                # 命令式审批门（ApprovalRequiredToolset）调度时无法预知，落到这只能提示走前台
                return f"工具 {original_name} 需要审批，无法后台执行，请改用前台版本 {original_name}。"
            except CallDeferred:
                # ask_user 这类工具靠抛 CallDeferred 把调用交给人/外部，离开图执行路径就成了哑弹
                return f"工具 {original_name} 需要与用户或外部直接交互，无法后台执行，请改用前台版本 {original_name}。"
            return value if isinstance(value, str) else str(value)

        task_id = ctx.deps.background.start(original_name, tool_args, run())
        return {
            "task_id": task_id,
            "status": "running",
            "note": "结果完成后会自动注入上下文并唤醒你，无需轮询；如需结果请先结束本轮回复。"
            "task_id 与 Shell 的 command_id 无关，不能用于 check_command/stop_command。",
        }


def _results_text(results: list[BackgroundResult]) -> str:
    sections = []
    for result in results:
        status = "被取消" if result.cancelled else ("出错" if result.is_error else "完成")
        sections.append(f"任务 {result.task_id}（{result.tool_name}）{status}：\n{result.output}")
    # 尾部换行：恢复会话时这段文本渲染成系统提示行，与后续汇报之间留出空行
    return "以下后台任务已有结果，请基于结果继续：\n\n" + "\n\n".join(sections) + "\n"


@dataclass
class Background(AbstractCapability[CodingAgentDeps]):
    """后台执行能力：Background_ 变体 + 结果回灌 + 管理工具。

    要审批的后台工具请用声明式 requires_approval=True：审批前置到调度时
    （批的是"以后台方式用这组参数启动"），批准后任务无人值守跑完。
    """

    extra_tools: Sequence[str] = ("run_command",)

    def get_wrapper_toolset(self, toolset: AbstractToolset[CodingAgentDeps]) -> AbstractToolset[CodingAgentDeps]:
        return BackgroundableToolset(wrapped=toolset, extra_tools=frozenset(self.extra_tools))

    def get_toolset(self) -> FunctionToolset[CodingAgentDeps]:
        async def list_background_tasks(ctx: RunContext[CodingAgentDeps]) -> str:
            """列出仍在后台运行的任务。仅在用户询问进度或准备取消时调用；不要用它轮询等待结果。

            return:
                task_id、工具名、参数、已运行秒数
            """
            tasks = ctx.deps.background.list_tasks()
            if not tasks:
                return "当前没有运行中的后台任务。"
            return "\n".join(
                f"{t['task_id']} | {t['tool_name']} | 已运行 {t['elapsed_seconds']}s | 参数: {t['args']}"
                for t in tasks
            )

        async def cancel_background_task(ctx: RunContext[CodingAgentDeps], task_id: str) -> str:
            """取消一个仍在运行的后台任务。

            Args:
                task_id: Background_ 工具返回的任务 id
            """
            if ctx.deps.background.cancel(task_id):
                return f"已取消后台任务 {task_id}。"
            return f"取消失败：任务 {task_id} 不存在或已结束。"

        return FunctionToolset(tools=[list_background_tasks, cancel_background_task])
    async def before_model_request(
        self,
        ctx: RunContext[CodingAgentDeps],
        request_context: ModelRequestContext,
    ) -> ModelRequestContext:
        """忙碌路径：下一次模型请求前把已结束的后台结果注入上下文。"""
        results = ctx.deps.background.drain_finished()
        if results:
            request_context.messages.append(
                ModelRequest(
                    parts=[UserPromptPart(_results_text(results))],
                    metadata={"source": BACKGROUND_TASK_SOURCE},
                )
            )
        return request_context


def background(extra_tools: Sequence[str] = ("run_command",)) -> Background:
    """加载后台执行能力；extra_tools 按名字额外标记（metadata backgroundable 之外的口子）。"""
    return Background(extra_tools=extra_tools)
