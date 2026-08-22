"""CliApp：开箱即用的 Claude Code 风格聊天界面基类。

子类只需实现 handle_input()，在里边用 await self.start_assistant() /
start_tool_call() / show_tool_call() / show_system() 输出内容；界面、
主题、历史、下拉框、/model 弹窗、状态栏全部内置。
"""


from typing import cast

from pydantic_ai import ToolCallPart
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.theme import Theme
from textual.widgets import Input, Markdown, Static

# get_current_worker 的返回类型在 textual 源码里没给 Worker 填泛型参数，
# 导入符号会被报 partially unknown —— 库的类型缺口，局部忽略，调用点用 cast 收窄。
from textual.worker import (  # pyright: ignore[reportUnknownVariableType]
    Worker,
    get_current_worker,
)

from .inputs import CommandDropdown, HistoryInput
from .modal import ApprovalModal, ModelSelectModal
from .theme import KIMI_THEME
from .utils import format_num
from .widgets import (
    AssistantMessage,
    ChatScroll,
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
        self._answer_stream = None
        self._finished = False

    def _check_cancelled(self) -> bool:
        worker = cast(Worker[None], get_current_worker())
        return worker is not None and worker.is_cancelled

    async def write_thinking(self, text: str) -> None:
        """累加思考内容（可多次调用）。首个字符到达前整行隐藏。"""
        if self._finished or self._check_cancelled():
            return
        if not self._thinking:
            self._message.query_one(".thinking-row").remove_class("stream-pending")
        self._thinking += text
        self._message.query_one("#thinking-content", Static).update(self._thinking)

    async def write_answer(self, text: str) -> None:
        """累加 Markdown 回答（可多次调用）。首个 chunk 到达前整行隐藏。"""
        if self._finished or self._check_cancelled():
            return
        if self._answer_stream is None:
            self._message.query_one(".answer-row").remove_class("stream-pending")
            self._answer_stream = Markdown.get_stream(
                self._message.query_one("#answer-md", Markdown)
            )
        await self._answer_stream.write(text)

    async def finish(self) -> None:
        """收尾：关掉 Markdown 流。重复调用安全。"""
        if self._finished:
            return
        self._finished = True
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
        worker = cast(Worker[None], get_current_worker())
        return worker is not None and worker.is_cancelled

    async def write_args(self, chunk: str) -> None:
        """流式累加参数文本（可多次调用）。"""
        if self._check_cancelled():
            return
        self._message.append_args(chunk)

    async def show_result(self, result: str) -> None:
        """补显示工具返回结果。"""
        if self._check_cancelled():
            return
        self._message.set_result(result)

    async def show_diff(self, diff: str) -> None:
        """显示编辑工具的 diff（红绿行）。"""
        if self._check_cancelled():
            return
        self._message.set_diff(diff)

    async def show_pending(self) -> None:
        """标记该调用处于"等待批准/外部执行"状态（deferred 工具）。"""
        if self._check_cancelled():
            return
        self._message.set_pending()


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
        height: 3;
        background: transparent;
        border: round #7a8391;
        padding: 0 1;
        margin: 0 1 0 1;
    }
    #user-input {
        width: 1fr;
        height: auto;
        border: none;
        padding: 0;
        background: transparent;
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
        commands: list[tuple[str, str]] | None = None,
        theme: Theme | None = KIMI_THEME,
    ) -> None:
        super().__init__()
        self.title_text = title
        self.model = model
        self.version = version
        self._commands = list(commands or [])
        if not any(name == "model" for name, _ in self._commands):
            self._commands.extend(BUILTIN_COMMANDS)
        self._message_counter = 0
        self._active_handles: list[AssistantHandle] = []
        if theme is not None:
            self.register_theme(theme)
            self.theme = theme.name

    def on_mount(self) -> None:
        """启动后自动聚焦输入框。"""
        self.query_one("#user-input", HistoryInput).focus()

    def compose(self) -> ComposeResult:
        with ChatScroll(id="chat-scroll"):
            yield WelcomeBox(title=self.title_text, model=self.model, version=self.version)
        with Vertical(id="input-area"):
            yield CommandDropdown(self._commands, id="command-dropdown")
            yield WorkingLine(id="working-line")
            with Horizontal(id="input-row"):
                yield Static(">", id="prompt")
                yield HistoryInput(placeholder="", id="user-input")
        yield StatusBar(model=self.model, context=_context_text(0), id="status-bar")

    # ---- 子类要实现的回调 ----

    async def handle_input(self, text: str) -> None:
        """处理一条普通输入。子类必须实现，框架会在 worker 里跑它。"""
        raise NotImplementedError

    async def handle_command(self, command: str) -> None:
        """处理斜杠命令（/model 内置弹窗，不会进这里）。默认提示未知命令。"""
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

    async def show_system(self, text: str) -> None:
        """显示一行灰色系统提示（错误 / 通知）。"""
        await self._scroll.mount(SystemMessage(text))
        self._scroll.anchor()

    def set_working(self, state: str | None) -> None:
        """输入框上方的运行状态行：idle/thinking/tool/working，None 收起。"""
        line = self.query_one("#working-line", WorkingLine)
        if state is None:
            line.hide()
        else:
            line.show_state(state)

    async def ask_approval(self, call: ToolCallPart) -> bool:
        """弹窗询问是否批准这一条工具调用：True 批准 / False 拒绝。多条挂起逐条问。"""
        return await self.push_screen_wait(ApprovalModal(call))

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
        self.set_status(context=_context_text(tokens))

    # ---- 框架内部：输入分发 ----

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """输入变化时，根据内容决定是否显示命令下拉。"""
        if event.input.id != "user-input":
            return
        dropdown = self.query_one("#command-dropdown", CommandDropdown)
        dropdown.filter(event.value)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value.strip()

        input_widget = self.query_one("#user-input", HistoryInput)
        input_widget.push_history(user_text)
        input_widget.value = ""

        if not user_text:
            return

        if user_text.startswith("/"):
            command = user_text[1:]
            if command == "model":
                self.push_screen(ModelSelectModal(current_model=self.model))
            else:
                await self.handle_command(command)
            self._scroll.anchor()
            return

        await self._scroll.mount(UserMessage(user_text))
        self._scroll.anchor()
        self.run_worker(self._run_handle_input(user_text))

    async def _run_handle_input(self, text: str) -> None:
        """在 worker 里跑用户代码；结束时给没收尾的 assistant 兜底 finish。"""
        try:
            await self.handle_input(text)
        finally:
            for handle in self._active_handles:
                await handle.finish()
            self._active_handles.clear()
            self.set_working(None)  # 兜底：worker 结束（含取消）时一定收掉状态行
