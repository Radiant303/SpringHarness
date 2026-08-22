"""聊天区组件：欢迎框、用户消息、AI 消息、工具调用消息、状态栏、滚动区。

代码从 step12_final.py 提炼，行为一致；WelcomeBox / StatusBar 把原来写死的
演示数据换成了构造参数，ToolCallMessage 是新增组件。
"""

from pathlib import Path
from typing import Any, ClassVar, cast

from rich.spinner import Spinner
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, HorizontalGroup, Vertical, VerticalScroll
from textual.highlight import highlight
from textual.reactive import Reactive, ReactiveType
from textual.widget import Widget
from textual.widgets import Static

from .cjk_wrap import CJKMarkdown, CJKStatic, DiffHighlightTheme
from .theme import ACCENT, GRAY


class WelcomeBox(Vertical):
    """顶部欢迎信息框：蓝色边框 + logo + 信息。"""

    DEFAULT_CSS = """
    WelcomeBox {
        width: 1fr;
        height: auto;
        background: transparent;
        border: round #4a9eff;
        padding: 1 2;
        margin: 1 1 0 1;
    }
    WelcomeBox .logo {
        width: 7;
        height: 2;
        background: #4a9eff;
        color: #1b1e24;
    }
    WelcomeBox .welcome-text {
        width: 1fr;
        height: auto;
        margin-left: 1;
    }
    WelcomeBox .info {
        width: 1fr;
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        title: str = "Kimi Code",
        model: str = "",
        version: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._model = model
        self._version = version

    def compose(self) -> ComposeResult:
        cwd = Path.cwd()
        with HorizontalGroup():
            yield Static(" ▪  ▪ ", classes="logo")
            with Vertical(classes="welcome-text"):
                yield Static(Text(f"Welcome to {self._title}!", style=f"bold {ACCENT}"))
                yield Static(Text("Send /help for help information.", style=GRAY))
        yield Static(
            Text.assemble(
                ("Directory: ", GRAY), (f"{cwd}\n", "#9aa3b0"),
                ("Session:   ", GRAY), ("session_xxx\n", "#9aa3b0"),
                ("Model:     ", GRAY), (f"{self._model}\n", "#9aa3b0"),
                ("Version:   ", GRAY), (self._version, "#9aa3b0"),
            ),
            classes="info",
        )


class UserMessage(CJKStatic):
    """用户消息：黄色 ✦ 开头。"""

    DEFAULT_CSS = """
    UserMessage {
        width: 1fr;
        height: auto;
        margin: 1 1 0 1;
    }
    """

    def __init__(self, text: str, **kwargs: Any) -> None:
        content = Text.assemble(
            ("✨ ", "bold yellow"),
            (text, "bold #FFCB6B"),
        )
        super().__init__(content, **kwargs)


class AssistantMessage(Vertical):
    """AI 消息：thinking（● 灰点 + 暗色斜体）+ 带 ● 的回答。"""

    DEFAULT_CSS = """
    AssistantMessage {
        width: 1fr;
        height: auto;
        margin: 0 1 1 1;
    }
    AssistantMessage .stream-pending {
        display: none;
    }
    AssistantMessage .thinking-row {
        width: 1fr;
        height: auto;
        margin-top: 1;
    }
    AssistantMessage .thinking-bullet {
        width: auto;
        height: auto;
        color: #7a8391;
        padding: 0 1 0 0;
    }
    AssistantMessage #thinking-content {
        width: 1fr;
        height: auto;
        color: #7a8391;
        text-style: italic;
    }
    AssistantMessage .answer-row {
        width: 1fr;
        height: auto;
        margin-top: 1;
    }
    AssistantMessage .assistant-bullet {
        width: auto;
        height: auto;
        color: ansi_default;
        padding: 0 1 0 0;
    }
    AssistantMessage Markdown {
        width: 1fr;
        height: auto;
        padding: 0;
        background: transparent;
    }
    AssistantMessage MarkdownParagraph:last-child {
        margin-bottom: 0;
    }
    """

    def compose(self) -> ComposeResult:
        with HorizontalGroup(classes="thinking-row stream-pending"):
            yield Static("●", classes="thinking-bullet")
            yield CJKStatic(id="thinking-content")
        with HorizontalGroup(classes="answer-row stream-pending"):
            yield Static("●", classes="assistant-bullet")
            yield CJKMarkdown(id="answer-md")


class ToolCallMessage(Vertical):
    """工具调用消息：一行 ⚡ ToolName(参数摘要)，结果灰字缩进、超长截断。

    两种用法：
    - 静态：构造时直接给 args / result（show_tool_call 走这条路）；
    - 流式：构造时只给 name，之后用 append_args() 逐段累加参数、
      set_result() 后补结果（start_tool_call 返回的句柄走这条路）。
    """

    MAX_RESULT_LINES = 5
    MAX_ARGS_LEN = 40

    DEFAULT_CSS = """
    ToolCallMessage {
        width: 1fr;
        height: auto;
        margin: 0 1 1 1;
    }
    ToolCallMessage .tool-head {
        width: 1fr;
        height: auto;
        margin-top: 1;
    }
    ToolCallMessage .tool-result {
        width: 1fr;
        height: auto;
        padding-left: 2;
        color: #7a8391;
    }
    ToolCallMessage .tool-diff {
        width: 1fr;
        height: auto;
        padding-left: 2;
    }
    ToolCallMessage .tool-pending {
        width: 1fr;
        height: auto;
        padding-left: 2;
        color: #e5c07b;
    }
    """

    def __init__(self, name: str, args: str = "", result: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._name = name
        self._args = args
        self._result = result
        self._diff: str | None = None

    def compose(self) -> ComposeResult:
        yield CJKStatic(self._render_head(), classes="tool-head")
        if self._result:
            yield CJKStatic(self._render_result(), classes="tool-result")

    def _render_head(self) -> Text:
        args = self._args
        if len(args) > self.MAX_ARGS_LEN:
            args = args[: self.MAX_ARGS_LEN - 1] + "…"
        return Text.assemble(
            ("⚡ ", ACCENT),
            (self._name, f"bold {ACCENT}"),
            (f"({args})", "#9aa3b0"),
        )

    def _render_result(self) -> str:
        lines = (self._result or "").splitlines()
        hidden = len(lines) - self.MAX_RESULT_LINES
        if hidden > 0:
            lines = lines[: self.MAX_RESULT_LINES] + [f"… (还有 {hidden} 行)"]
        return "\n".join(lines)

    def append_args(self, chunk: str) -> None:
        """流式累加参数文本并刷新标题行（超长部分显示为 …）。"""
        self._args += chunk
        self.query_one(".tool-head", CJKStatic).update(self._render_head())

    def set_result(self, result: str) -> None:
        """补显示工具返回结果；重复调用以最后一次为准。结果到达即撤下等待标记。"""
        self._result = result
        rendered = self._render_result()
        if self.query(".tool-pending"):
            self.query_one(".tool-pending", CJKStatic).remove()
        if self.query(".tool-result"):
            self.query_one(".tool-result", CJKStatic).update(rendered)
        else:
            self.mount(CJKStatic(rendered, classes="tool-result"))

    def set_pending(self) -> None:
        """标记为"等待批准/外部执行"（deferred 工具调用暂停）；重复调用幂等。"""
        if not self.query(".tool-pending"):
            self.mount(CJKStatic("⏸ 等待批准", classes="tool-pending"))

    def set_diff(self, diff_text: str) -> None:
        """显示编辑工具的 diff（红绿行）；重复调用以最后一次为准。

        时序上 diff 在工具结果之前到达（参数完整时即生成），直接追加挂载即可。
        """
        self._diff = diff_text
        content = highlight(diff_text, language="diff", theme=DiffHighlightTheme)
        if self.query(".tool-diff"):
            self.query_one(".tool-diff", CJKStatic).update(content)
        else:
            self.mount(CJKStatic(content, classes="tool-diff"))


class WorkingLine(Static):
    """输入框上方左侧的运行状态行：spinner 动画 + 状态标签 + 一句话。

    由 CliApp.set_working(state) 驱动：state 是 STATES 的键，None 时整行隐藏。
    spinner 用 rich 的 Spinner（moon/dots/line），它按时间取帧，
    所以定时器里反复 update 同一个 Spinner 对象就能形成动画。
    """

    STATES: ClassVar[dict[str, tuple[str, str, str]]] = {
        "idle": ("moon", "", "We see the first gaze, feel life's power transcend."),
        "thinking": ("dots", "Thinking...", "The quiet mind is the calling card of deep thought."),
        "tool": ("line", "Using Tool...", "Give me a place to stand, and I will move Earth."),
        "working": ("dots", "Working...", "It always seems impossible until it is done by us."),
    }

    DEFAULT_CSS = """
    WorkingLine {
        width: 1fr;
        height: 1;
        padding: 0;
        margin: 1 1 0 1;
        background: transparent;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self.state: str | None = None
        self._spinner: Spinner | None = None
        self.display = False

    def on_mount(self) -> None:
        self.set_interval(1 / 12, self._advance)

    def show_state(self, state: str) -> None:
        if state == self.state:
            return  # 同状态高频重复调用（每个 delta 一次），重建 spinner 会卡住动画
        spinner, label, text = self.STATES[state]
        self.state = state
        parts: list[tuple[str, str]] = []
        if label:
            parts.append((f"{label} ", f"bold {ACCENT}"))
        parts.append(("· ", GRAY))
        parts.append((text, f"italic {GRAY}"))
        self._spinner = Spinner(spinner, text=Text.assemble(*parts))
        self.display = True
        self._advance()

    def hide(self) -> None:
        self.state = None
        self._spinner = None
        self.display = False

    def _advance(self) -> None:
        if self._spinner is not None:
            self.update(self._spinner)


class SystemMessage(CJKStatic):
    """系统提示行：灰色文字（错误 / 提示 / 命令回显都用它）。"""

    DEFAULT_CSS = """
    SystemMessage {
        width: 1fr;
        height: auto;
        margin: 0 1;
        color: #7a8391;
    }
    """

    def __init__(self, text: str, **kwargs: Any) -> None:
        super().__init__(Text(text, style=GRAY), **kwargs)


class ChatScroll(VerticalScroll):
    """聊天滚动区：修复 anchor() 的一个小 bug。

    anchor() 让滚动区一直吸底；但 Textual 的合成器在「内容不足一屏」时
    会把 scroll_y 直接设成负数（set_reactive 绕过了 0 下限的校验），表现为：
    第一次发消息后，上面的内容整体往下挪、顶部空出一片。
    这里把负的滚动值挡回去即可。

    滚动条隐藏（scrollbar-size: 0）：吸底场景不需要它，省两列空间。
    """

    DEFAULT_CSS = """
    ChatScroll {
        scrollbar-size: 0 0;
    }
    """

    def set_reactive(self, reactive: Reactive[ReactiveType], value: ReactiveType) -> None:
        if (
            isinstance(value, (int, float))
            and value < 0
            and (reactive is Widget.scroll_y or reactive is Widget.scroll_target_y)
        ):
            value = cast(ReactiveType, 0)
        super().set_reactive(reactive, value)


class StatusBar(Horizontal):
    """底部状态栏：左侧信息 + 右侧上下文，字段可用 update() 局部更新。"""

    DEFAULT_CSS = """
    StatusBar {
        width: 1fr;
        height: 1;
        background: transparent;
        padding: 0 1;
    }
    StatusBar .status-left {
        width: 1fr;
        height: 1;
        content-align: left middle;
    }
    StatusBar .status-right {
        width: auto;
        height: 1;
        content-align: right middle;
    }
    """

    def __init__(
        self,
        model: str = "",
        directory: str | None = None,
        git_branch: str = "",
        context: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._model = model
        self._directory = directory if directory is not None else str(Path.cwd())
        self._git_branch = git_branch
        self._context_text = context

    def compose(self) -> ComposeResult:
        yield Static(self._render_left(), classes="status-left")
        yield Static(Text(self._context_text, style=GRAY), classes="status-right")

    def _render_left(self) -> Text:
        parts: list[tuple[str, str]] = [(self._model, "default")]
        tail = f"{self._directory}  {self._git_branch}".rstrip()
        parts.append((f"  {tail}", GRAY))
        return Text.assemble(*parts)

    def update(
        self,
        model: str | None = None,
        directory: str | None = None,
        git_branch: str | None = None,
        context: str | None = None,
    ) -> None:
        """局部更新状态栏字段（None 表示保持原值）。"""
        if model is not None:
            self._model = model
        if directory is not None:
            self._directory = directory
        if git_branch is not None:
            self._git_branch = git_branch
        if context is not None:
            self._context_text = context
        self.query_one(".status-left", Static).update(self._render_left())
        self.query_one(".status-right", Static).update(Text(self._context_text, style=GRAY))
