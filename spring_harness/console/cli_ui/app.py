"""CliApp：开箱即用的 Claude Code 风格聊天界面基类。

子类只需实现 handle_input()，在里边用 await self.start_assistant() /
start_tool_call() / show_tool_call() / show_system() 输出内容；界面、
主题、历史、下拉框、/model 弹窗、状态栏全部内置。
"""


import time
from typing import cast

from pydantic_ai import ToolCallPart
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.theme import Theme
from textual.widgets import Markdown, Static, TextArea

# get_current_worker 的返回类型在 textual 源码里没给 Worker 填泛型参数，
# 导入符号会被报 partially unknown —— 库的类型缺口，局部忽略，调用点用 cast 收窄。
from textual.worker import (
    NoActiveWorker,
    Worker,
    get_current_worker,
)

from .inputs import CommandDropdown, HistoryInput
from .modal import ApprovalModal
from .theme import KIMI_THEME
from .utils import LinePacer, format_num
from .widgets import (
    AssistantMessage,
    ChatScroll,
    PlanMessage,
    StatusBar,
    SystemMessage,
    ToolCallMessage,
    UserMessage,
    WelcomeBox,
    WorkingLine,
)

BUILTIN_COMMANDS = [
    ("model", "Switch LLM model"),
]

MAX_CONTEXT_TOKENS = 256_000  # 模型上下文窗口大小


def _context_text(tokens: int, max_tokens: int = MAX_CONTEXT_TOKENS) -> str:
    """状态栏右侧的上下文占用文本：context: 3% (8192/256k)。"""
    pct = round(tokens / max_tokens * 100)
    return f"context: {pct}% ({format_num(tokens)}/{format_num(max_tokens)})"


class AssistantHandle:
    """一条 AI 消息的写入句柄：thinking 和回答分开流式累加。

    由 ``await app.start_assistant()`` 创建；``finish()`` 必须调用
    （框架在 worker 结束时会兜底，但请显式调用）。
    """

    def __init__(self, message: AssistantMessage) -> None:
        self._message = message
        self._thinking = ""
        self._thinking_start: float | None = None
        self._answer_stream = None
        self._finished = False
        self._answer_pacer = LinePacer(self._flush_answer)
    def _check_cancelled(self) -> bool:
        try:
            worker = cast(Worker[None], get_current_worker())
        except NoActiveWorker:
            return False
        return worker is not None and worker.is_cancelled

    async def _flush_thinking(self) -> None:
        """thinking 渲染用的是全文 self._thinking（Static 更新便宜，
        不像 Markdown 流要重解析，所以不走 LinePacer 逐行节奏）。
        首次 flush 才揭示整行：● 出现后必然跟着内容。"""
        self._message.query_one(".thinking-row").remove_class("stream-pending")
        self._message.query_one("#thinking-content", Static).update(
            Text(self._thinking.lstrip("\n"))
        )

    async def _flush_answer(self, batch: str) -> None:
        if self._answer_stream is not None:
            # 首次 flush 才揭示整行：● 出现后必然跟着内容
            self._message.query_one(".answer-row").remove_class("stream-pending")
            await self._answer_stream.write(batch)


    async def write_thinking(self, text: str) -> None:
        """累加思考内容（可多次调用）。首个字符到达前整行隐藏。"""
        if self._finished or self._check_cancelled():
            return
        if not self._thinking:
            self._thinking_start = time.monotonic()
        self._thinking += text
        # 包成 Text：思考文本里的 […] 会被 Static 按 Rich markup 解析而抛 MarkupError；
        # 去除首行换行。delta 一到就整段刷新，跟网络分块节奏走（成块感而非逐行）。
        await self._flush_thinking()

    async def write_answer(self, text: str) -> None:
        """累加 Markdown 回答（可多次调用）。首个 chunk 到达前整行隐藏。"""
        if self._finished or self._check_cancelled():
            return
        if self._answer_stream is None:
            self._answer_stream = Markdown.get_stream(
                self._message.query_one("#answer-md", Markdown)
            )
        self._answer_pacer.write(text)

    async def finish(self) -> None:
        """收尾：thinking 折叠成一行摘要（全文占屏），关掉 Markdown 流。重复调用安全。"""
        if self._finished:
            return
        self._finished = True
        await self._answer_pacer.drain()

        if self._thinking and self._thinking_start is not None:
            elapsed = time.monotonic() - self._thinking_start
            self._message.query_one("#thinking-content", Static).update(
                Text(f"Thought for {elapsed:.1f}s")
            )
        if self._answer_stream is not None:
            await self._answer_stream.stop()


class ToolCallHandle:
    """一条工具调用的写入句柄：args 流式累加，结果后补。

    由 ``await app.start_tool_call(name)`` 创建；方法签名与
    console/sink.py 的 ToolCallSink 协议一致，可直接当 sink 用。
    """

    def __init__(self, message: ToolCallMessage) -> None:
        self._message = message

    def _check_cancelled(self) -> bool:
        try:
            worker = cast(Worker[None], get_current_worker())
        except NoActiveWorker:
            return False
        return worker is not None and worker.is_cancelled

    async def write_args(self, chunk: str) -> None:
        """流式累加参数文本（可多次调用）。"""
        if self._check_cancelled():
            return
        self._message.append_args(chunk)

    async def show_result(self, result: str, is_error: bool = False) -> None:
        """补显示工具返回结果；is_error=True 标记失败（图标变红 ✗）。"""
        if self._check_cancelled():
            return
        await self._message.set_result(result, is_error=is_error)

    async def show_diff(self, diff: str) -> None:
        """显示编辑工具的 diff（红绿行）。"""
        if self._check_cancelled():
            return
        await self._message.set_diff(diff)

    async def show_pending(self) -> None:
        """标记该调用处于"等待批准/外部执行"状态（deferred 工具）。"""
        if self._check_cancelled():
            return
        await self._message.set_pending()


class CliApp(App[None]):
    """Claude Code / Kimi Code 风格的终端聊天 App 基类。

    用法::

        class MyBot(CliApp):
            async def handle_input(self, text: str) -> None:
                assistant = await self.start_assistant()
                await assistant.write_answer(f"你说的是：{text}")
                await assistant.finish()

        MyBot(title="My Bot", model="K3-256k", version="0.1.0").run()
    """

    CSS = """
    App {
        background: ansi_default;
    }
    MarkdownH1 {
        content-align: left middle;  /* 库默认居中，App 级 CSS 才能压住组件自带 DEFAULT_CSS */
    }
    Screen {
        layout: vertical;
        background: transparent;
    }
    #chat-scroll {
        width: 1fr;
        height: 1fr;
        padding: 0;
        background: transparent;
    }
    #input-area {
        width: 1fr;
        height: auto;
        padding: 0;
        background: transparent;
    }
    #input-row {
        width: 1fr;
        height: auto;
        max-height: 8;  /* 输入内容最多 6 行 + 上下边框 2 行 */
        background: transparent;
        border: round #7a8391;
        padding: 0 1;
        margin: 0 1 0 1;
    }
    #user-input {
        width: 1fr;
        height: auto;
        max-height: 6;
        border: none;
        padding: 0;
        background: transparent;
        scrollbar-size: 0 0;
    }
    #prompt {
        width: auto;
        height: auto;
        color: ansi_default;
        padding-right: 1;
    }
    """

    def __init__(
        self,
        title: str = "Kimi Code",
        model: str = "K3-256k",
        version: str = "0.34.0",
        max_context:int = MAX_CONTEXT_TOKENS,
        commands: list[tuple[str, str]] | None = None,
        theme: Theme | None = KIMI_THEME,
    ) -> None:
        super().__init__()
        # 鼠标滚轮每次滚动的行数（App 默认 2.0）
        self.scroll_sensitivity_y = 3.0
        self.title_text = title
        self.model = model
        self.version = version
        self.max_context = max_context
        # 会话短 id（如 session_f2ec8ac5），由子类在创建/切换会话后更新
        self.session_id = ""
        self._last_tokens = 0
        self._commands = list(commands or [])
        if not any(name == "model" for name, _ in self._commands):
            self._commands.extend(BUILTIN_COMMANDS)
        self._message_counter = 0
        self._active_handles: list[AssistantHandle] = []
        self._plan_widget: PlanMessage | None = None
        if theme is not None:
            self.register_theme(theme)
            self.theme = theme.name

    def on_mount(self) -> None:
        """启动后自动聚焦输入框。"""
        self.query_one("#user-input", HistoryInput).focus()

    def compose(self) -> ComposeResult:
        with ChatScroll(id="chat-scroll"):
            yield WelcomeBox(
                title=self.title_text, model=self.model,
                version=self.version, session=self.session_id,
            )
        with Vertical(id="input-area"):
            yield CommandDropdown(self._commands, id="command-dropdown")
            yield WorkingLine(id="working-line")
            with Horizontal(id="input-row"):
                yield Static(">", id="prompt")
                yield HistoryInput(placeholder="", id="user-input")
        yield StatusBar(model=self.model, context=_context_text(0, self.max_context), id="status-bar")

    # ---- 子类要实现的回调 ----

    async def handle_input(self, text: str) -> None:
        """处理一条普通输入。子类必须实现，框架会在 worker 里跑它。"""
        raise NotImplementedError

    async def handle_command(self, command: str) -> None:
        """处理斜杠命令（含 /model：框架只提供弹窗组件，切换逻辑归子类）。默认提示未知命令。"""
        await self.show_system(f"Unknown command: /{command}")

    # ---- 显示类方法（async，可在 handle_input 里直接 await）----

    @property
    def _scroll(self) -> ChatScroll:
        return self.query_one("#chat-scroll", ChatScroll)

    async def show_user(self, text: str) -> None:
        """手动补显示一条用户消息（提交时框架已自动显示，一般不需要调）。"""
        await self._scroll.mount(UserMessage(text))
        self._scroll.anchor()

    async def start_assistant(self) -> AssistantHandle:
        """开一条新的 AI 消息，返回写入句柄。"""
        self._message_counter += 1
        message = AssistantMessage(id=f"assistant-{self._message_counter}")
        await self._scroll.mount(message)
        self._scroll.anchor()
        handle = AssistantHandle(message)
        self._active_handles.append(handle)
        return handle

    async def start_tool_call(self, name: str) -> ToolCallHandle:
        """开一条新的工具调用消息，返回写入句柄（args 流式累加、结果后补）。"""
        message = ToolCallMessage(name)
        await self._scroll.mount(message)
        self._scroll.anchor()
        return ToolCallHandle(message)

    async def show_tool_call(self, name: str, args: str = "", result: str | None = None) -> None:
        """显示一条工具调用：⚡ Name(参数) + 灰字缩进的结果。"""
        await self._scroll.mount(ToolCallMessage(name, args, result))
        self._scroll.anchor()

    async def show_plan(self, items: list) -> None:
        """显示计划清单。组件还在聊天末尾就原地更新；若后面已有新内容
        （工具调用/回答），在末尾挂一份最新快照，旧块留作历史（同 codex
        每次 update_plan 追加新块的语义，保证最新计划始终贴近队尾可见）。
        items 见 PlanMessage。
        """
        if not items:
            return
        widget = self._plan_widget
        children = self._scroll.children
        if widget is not None and widget.is_attached and children and children[-1] is widget:
            await widget.update_items(items)
        else:
            self._plan_widget = PlanMessage(items)
            await self._scroll.mount(self._plan_widget)
        self._scroll.anchor()

    async def show_system(self, text: str) -> None:
        """显示一行灰色系统提示（错误 / 通知）。"""
        await self._scroll.mount(SystemMessage(text))
        self._scroll.anchor()

    def set_working(self, state: str | None) -> None:
        """输入框上方的运行状态行；None 隐藏内容但保留一行占位。"""
        line = self.query_one("#working-line", WorkingLine)
        if state is None:
            line.hide()
        else:
            line.show_state(state)

    async def ask_approval(self, call: ToolCallPart, diff: str | None = None) -> bool:
        """弹窗询问是否批准这一条工具调用：True 批准 / False 拒绝。多条挂起逐条问。

        diff：编辑类工具的改动预览（调用方用 renderer.make_diff 生成），随参数一起展示。
        """
        return await self.push_screen_wait(ApprovalModal(call, diff=diff))

    def set_status(
        self,
        model: str | None = None,
        directory: str | None = None,
        git_branch: str | None = None,
        context: str | None = None,
    ) -> None:
        """更新状态栏字段（None 表示保持原值）。"""
        self.query_one("#status-bar", StatusBar).update(
            model=model, directory=directory, git_branch=git_branch, context=context
        )

    def update_context(self, tokens: int) -> None:
        """更新状态栏右侧的上下文占用显示（token 数）。"""
        self._last_tokens = tokens
        self.set_status(context=_context_text(tokens,max_tokens=self.max_context))

    def set_model(self, model: str, max_context: int) -> None:
        """切换模型时候更新面板模型名称和上下文信息"""
        self.model = model
        self.max_context = max_context
        self.set_status(model=model)
        self.set_status(context=_context_text(self._last_tokens, self.max_context))

    # ---- 框架内部：输入分发 ----

    @on(TextArea.Changed)
    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """输入变化时：调整输入框高度（最多 6 行）+ 按需显示命令下拉。"""
        if event.text_area.id != "user-input":
            return
        input_widget = event.text_area
        # 高度跟随文档行数；超长行软换行占的额外行不细算（长粘贴已折叠成占位符）
        input_widget.styles.height = max(1, min(6, input_widget.document.line_count))
        self.query_one("#command-dropdown", CommandDropdown).filter(input_widget.text)

    async def on_history_input_submitted(self, event: HistoryInput.Submitted) -> None:
        display_text = event.value.strip()
        if not display_text:
            return

        input_widget = event.input
        input_widget.push_history(display_text)
        input_widget.text = ""
        # 占位符还原：聊天区和模型都显示/收到完整粘贴内容；
        # 占位符版本只留在输入框和历史里，↑ 翻回来时仍是紧凑形态
        full_text = input_widget.expand_pastes(display_text)

        if display_text.startswith("/"):
            await self.handle_command(display_text[1:])
            self._scroll.anchor()
            return

        await self._scroll.mount(UserMessage(full_text))
        self._scroll.anchor()
        self.run_worker(self._run_handle_input(full_text))

    async def _run_handle_input(self, text: str) -> None:
        """在 worker 里跑用户代码；结束时给没收尾的 assistant 兜底 finish。"""
        try:
            await self.handle_input(text)
        except Exception as e:
            # 一次运行失败（如工具重试超限 UnexpectedModelBehavior）不应拖垮整个 TUI，
            # 降级为聊天区的一条系统消息
            await self.show_system(f"❌ {type(e).__name__}: {e}")
        finally:
            for handle in self._active_handles:
                await handle.finish()
            self._active_handles.clear()
            self.set_working(None)  # 兜底：worker 结束（含取消）时一定收掉状态行
