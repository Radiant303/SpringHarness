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
    """顶部欢迎信息框：欢迎语和运行信息。"""

    DEFAULT_CSS = """
    WelcomeBox {
        width: 1fr;
        height: auto;
        background: transparent;
        border: round #4a9eff;
        padding: 1 2;
        margin: 1 1 0 1;
    }
    WelcomeBox .welcome-text {
        width: 1fr;
        height: auto;
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
        session: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._model = model
        self._version = version
        self._session = session

    def compose(self) -> ComposeResult:
        cwd = Path.cwd()
        with Vertical(classes="welcome-text"):
            yield Static(Text(f"Welcome to {self._title}!", style=f"bold {ACCENT}"))
            yield Static(Text("Send /help for help information.", style=GRAY))
        lines: list[tuple[str, str]] = [
            ("Directory: ", GRAY), (f"{cwd}\n", "default"),
        ]
        if self._session:
            lines += [("Session:   ", GRAY), (f"{self._session}\n", "default")]
        lines += [
            ("Model:     ", GRAY), (f"{self._model}\n", "default"),
            ("Version:   ", GRAY), (self._version, "default"),
        ]
        yield Static(Text.assemble(*lines), classes="info")


class UserMessage(CJKStatic):
    """用户消息：黄色 ✦ 开头。"""

    DEFAULT_CSS = """
    UserMessage {
        width: 1fr;
        height: auto;
        margin: 1 1 1 1;
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
        margin-top: 0;
    }
    AssistantMessage .thinking-bullet {
        width: auto;
        height: auto;
        color: ansi_bright_black;
        padding: 0 1 0 0;
    }
    AssistantMessage #thinking-content {
        width: 1fr;
        height: auto;
        color: ansi_bright_black;
        text-style: italic;
    }
    AssistantMessage .answer-row {
        width: 1fr;
        height: auto;
        margin-top: 0;
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


class PlanMessage(Vertical):
    """计划清单：● Plan (2/5) 标题行 + 每步一行（图标列 + 文本列）。

    样式仿 codex 的 PlanUpdateCell：完成项 ✓ 暗色删除线、进行中 □ 青色加粗
    （有 active_form 显示 active_form）、待办 □ 暗色；另补取消 ✗、阻塞黄色。
    每步是独立的 HorizontalGroup（图标列固定 2 格），长文本换行后对齐文本列，
    同 codex 快照里的悬挂缩进效果。
    items 鸭子类型：需有 .content/.status/.active_form，status 为 str 枚举。
    """

    DEFAULT_CSS = """
    PlanMessage {
        width: 1fr;
        height: auto;
        margin: 0 1 1 1;
    }
    PlanMessage .plan-head {
        width: 1fr;
        height: auto;
    }
    PlanMessage .plan-rows {
        width: 1fr;
        height: auto;
        padding-left: 2;
    }
    PlanMessage .plan-icon {
        width: 2;
        height: auto;
    }
    PlanMessage .plan-label {
        width: 1fr;
        height: auto;
    }
    """

    _STATUS_STYLE: ClassVar[dict[str, tuple[str, str]]] = {
        "completed": ("✓", "dim strike"),
        "in_progress": ("□", "bold cyan"),
        "pending": ("□", "dim"),
        "cancelled": ("✗", "dim strike"),
        "blocked": ("□", "yellow"),
    }

    def __init__(self, items: list[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._items = list(items)

    def compose(self) -> ComposeResult:
        yield Static(self._render_head(), classes="plan-head")
        yield Vertical(classes="plan-rows")

    async def on_mount(self) -> None:
        await self._rebuild_rows()

    async def update_items(self, items: list[Any]) -> None:
        """原地刷新清单（组件未挂载时静默丢弃，下次事件会重建）。"""
        self._items = list(items)
        if self.is_attached:
            self.query_one(".plan-head", Static).update(self._render_head())
            await self._rebuild_rows()

    async def _rebuild_rows(self) -> None:
        rows = self.query_one(".plan-rows")
        await rows.remove_children()
        await rows.mount_all(self._render_row(item) for item in self._items)

    def _render_head(self) -> Text:
        total = len(self._items)
        done = sum(1 for i in self._items if self._status(i) == "completed")
        text = Text()
        text.append("● ", style=ACCENT)
        text.append("Plan ", style="bold")
        text.append(f"{done}/{total}", style=GRAY)
        return text

    def _render_row(self, item: Any) -> HorizontalGroup:
        status = self._status(item)
        icon, style = self._STATUS_STYLE.get(status, ("○", "dim"))
        label = item.active_form if status == "in_progress" and item.active_form else item.content
        # Text 不解析 markup，计划文本里的 […] 不会触发 MarkupError
        return HorizontalGroup(
            Static(Text(f"{icon} ", style=style), classes="plan-icon"),
            CJKStatic(Text(label, style=style), classes="plan-label"),
        )

    @staticmethod
    def _status(item: Any) -> str:
        status = getattr(item, "status", "pending")
        return getattr(status, "value", str(status))


class TeachingMessage(Vertical):
    """教学单元面板：● Teach <title> vN (m/n) 标题行 + 每个 objective 一行掌握度。

    样式与 PlanMessage 同构：已达要求 ✓ 暗色删除线、已认证但未达要求 □ 青色加粗、
    未认证 □ 暗色；行尾灰字标注掌握度 [D1/D2] 与提示用量 hints L1×2。
    unit 鸭子类型：需有 .title/.version/.status/.objectives/.hints；
    objective 需有 .id/.text/.mastery_required/.mastery_achieved（str 枚举）。
    """

    DEFAULT_CSS = """
    TeachingMessage {
        width: 1fr;
        height: auto;
        margin: 0 1 1 1;
    }
    TeachingMessage .teach-head {
        width: 1fr;
        height: auto;
    }
    TeachingMessage .teach-rows {
        width: 1fr;
        height: auto;
        padding-left: 2;
    }
    TeachingMessage .teach-icon {
        width: 2;
        height: auto;
    }
    TeachingMessage .teach-label {
        width: 1fr;
        height: auto;
    }
    """

    _ORDER: ClassVar[dict[str, int]] = {"D1": 1, "D2": 2, "D3": 3}

    def __init__(self, unit: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._unit = unit

    def compose(self) -> ComposeResult:
        yield Static(self._render_head(), classes="teach-head")
        yield Vertical(classes="teach-rows")

    async def on_mount(self) -> None:
        await self._rebuild_rows()

    async def update_unit(self, unit: Any) -> None:
        """原地刷新面板（组件未挂载时静默丢弃，下次事件会重建）。"""
        self._unit = unit
        if self.is_attached:
            self.query_one(".teach-head", Static).update(self._render_head())
            await self._rebuild_rows()

    async def _rebuild_rows(self) -> None:
        rows = self.query_one(".teach-rows")
        await rows.remove_children()
        row_widgets = []
        for o in self._unit.objectives:
            row_widgets.append(self._render_row(o))
        await rows.mount_all(row_widgets)

    def _render_head(self) -> Text:
        objectives = self._unit.objectives
        done = 0
        for o in objectives:
            if self._met(o):
                done += 1
        text = Text()
        text.append("● ", style=ACCENT)
        text.append("Teach ", style="bold")
        text.append(f"{self._unit.title} ", style="bold")
        text.append(f"v{self._unit.version} · {done}/{len(objectives)}", style=GRAY)
        status = getattr(self._unit.status, "value", str(self._unit.status))
        if status == "closed":
            text.append(" · closed", style=GRAY)
        return text

    def _render_row(self, objective: Any) -> HorizontalGroup:
        met = self._met(objective)
        achieved = self._level(objective.mastery_achieved)
        if met:
            icon, style = "✓", "dim strike"
        elif achieved is not None:
            icon, style = "□", "bold cyan"
        else:
            icon, style = "□", "dim"
        label = Text()
        label.append(f"{objective.id} {objective.text}", style=style)
        if achieved is None:
            achieved_text = "-"
        else:
            achieved_text = achieved
        tail = f"  [{achieved_text}/{self._level(objective.mastery_required)}]"
        used = []
        for h in self._unit.hints:
            if h.objective_id == objective.id:
                used.append(h.level)
        if used:
            counts = {}
            for level in used:
                counts[level] = counts.get(level, 0) + 1
            parts = []
            for level in sorted(counts):
                parts.append(f"L{level}×{counts[level]}")
            tail += " · hints " + " ".join(parts)
        label.append(tail, style=GRAY)
        return HorizontalGroup(
            Static(Text(f"{icon} ", style=style), classes="teach-icon"),
            CJKStatic(label, classes="teach-label"),
        )

    def _met(self, objective: Any) -> bool:
        achieved = self._level(objective.mastery_achieved)
        required = self._level(objective.mastery_required)
        if achieved is None or required is None:
            return False
        return self._ORDER[achieved] >= self._ORDER[required]

    @staticmethod
    def _level(mastery: Any) -> str | None:
        if mastery is None:
            return None
        return getattr(mastery, "value", str(mastery))


class ToolCallMessage(Vertical):
    """工具调用消息：一行图标 + ToolName(参数摘要)，结果灰字缩进、超长截断。

    两种用法：
    - 静态：构造时直接给 args / result（show_tool_call 走这条路）；
    - 流式：构造时只给 name，之后用 append_args() 逐段累加参数、
      set_result() 后补结果（start_tool_call 返回的句柄走这条路）。

    完成态图标：运行中 ⚡（蓝）→ set_result() 后 ✓（绿）/ ✗（红，is_error=True）。
    """

    MAX_RESULT_LINES = 5
    MAX_LINE_CHARS = 80  # 单行字符上限：无换行的超长结果也要截断
    MAX_ARGS_LEN = 40

    _HEAD_ICONS: ClassVar[dict[str, tuple[str, str]]] = {
        "running": ("⚡ ", ACCENT),
        "ok": ("✓ ", "bold #98c379"),
        "error": ("✗ ", "bold #e06c75"),
    }

    DEFAULT_CSS = """
    ToolCallMessage {
        width: 1fr;
        height: auto;
        margin: 0 1 1 1;
    }
    ToolCallMessage .tool-head {
        width: 1fr;
        height: auto;
        margin-top: 0;
    }
    ToolCallMessage .tool-result {
        width: 1fr;
        height: auto;
        padding-left: 2;
        border-left: solid #3a3f4a;
        color: ansi_bright_black;
    }
    ToolCallMessage .tool-diff {
        width: 1fr;
        height: auto;
        padding-left: 2;
        border-left: solid #3a3f4a;
    }
    ToolCallMessage .tool-pending {
        width: 1fr;
        height: auto;
        padding-left: 2;
        border-left: solid #3a3f4a;
        color: #e5c07b;
    }
    """

    def __init__(self, name: str, args: str = "", result: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._name = name
        self._args = args
        self._result = result
        self._diff: str | None = None
        # 静态用法（构造即带 result）直接是完成态
        self._status = "running" if result is None else "ok"
        self._collapsed = False

    def compose(self) -> ComposeResult:
        yield CJKStatic(self._render_head(), classes="tool-head")
        if self._result:
            yield CJKStatic(self._render_result(), classes="tool-result")

    def _render_head(self) -> Text:
        args = self._args
        if len(args) > self.MAX_ARGS_LEN:
            args = args[: self.MAX_ARGS_LEN - 1] + "…"
        icon, icon_style = self._HEAD_ICONS[self._status]
        return Text.assemble(
            (icon, icon_style),
            (self._name, f"bold {ACCENT}"),
            (f"({args})", "default"),
        )

    def _render_result(self) -> Text:
        # 必须包成 Text：工具输出是任意文本，里面的 […] 会被 Static 按
        # Rich markup 解析，形如 capabilities=[hooks] 的内容直接抛 MarkupError
        lines = (self._result or "").splitlines()
        hidden = len(lines) - self.MAX_RESULT_LINES
        if hidden > 0:
            lines = lines[: self.MAX_RESULT_LINES] + [f"… (还有 {hidden} 行)"]
        # 行数之外再按字符兜底：无换行的超长单行也要截断
        lines = [
            line[: self.MAX_LINE_CHARS] + f" … (省略 {len(line) - self.MAX_LINE_CHARS} 字符)"
            if len(line) > self.MAX_LINE_CHARS
            else line
            for line in lines
        ]
        return Text("\n".join(lines))

    def append_args(self, chunk: str) -> None:
        """流式累加参数文本并刷新标题行（超长部分显示为 …）。"""
        self._args += chunk
        self.query_one(".tool-head", CJKStatic).update(self._render_head())

    async def set_result(self, result: str, is_error: bool = False) -> None:
        """补显示工具返回结果；重复调用以最后一次为准。结果到达即撤下等待标记、刷新完成态图标。"""
        self._result = result
        self._collapsed = False  # 新结果到达时恢复展开
        self._status = "error" if is_error else "ok"
        self.query_one(".tool-head", CJKStatic).update(self._render_head())
        rendered = self._render_result()
        if self.query(".tool-pending"):
            await self.query_one(".tool-pending", CJKStatic).remove()
        if self.query(".tool-result"):
            self.query_one(".tool-result", CJKStatic).update(rendered)
        else:
            await self.mount(CJKStatic(rendered, classes="tool-result"))

    async def set_pending(self) -> None:
        """标记为"等待批准/外部执行"（deferred 工具调用暂停）；重复调用幂等。"""
        if not self.query(".tool-pending"):
            # ⏸ 在 Windows Terminal 会被渲染成彩色 emoji 方块，用文字安全字符 ◆
            await self.mount(CJKStatic("◆ 等待批准", classes="tool-pending"))

    def collapse(self) -> None:
        """把结果收成一行摘要：run 结束、最终答案出现后由 CliSink.finish() 统一调用。

        执行过程中结果保持展开（实时反馈）；答案出来后历史细节不再重要，
        收起让对话更紧凑（Claude Code 同款行为）。重复调用幂等。
        """
        if not self._result or self._collapsed:
            return
        self._collapsed = True
        lines = self._result.splitlines()
        first = lines[0] if lines else ""
        summary = first[: self.MAX_LINE_CHARS]
        notes = []
        if len(lines) > 1:
            notes.append(f"共 {len(lines)} 行")
        if len(first) > self.MAX_LINE_CHARS:
            notes.append(f"共 {len(first)} 字符")
        if notes:
            summary += "  … (" + ", ".join(notes) + ")"
        if self.query(".tool-result"):
            self.query_one(".tool-result", CJKStatic).update(Text(summary))

    async def set_diff(self, diff_text: str) -> None:
        """显示编辑工具的 diff（红绿行）；重复调用以最后一次为准。

        时序上 diff 在工具结果之前到达（参数完整时即生成），直接追加挂载即可。
        """
        self._diff = diff_text
        content = highlight(diff_text, language="diff", theme=DiffHighlightTheme)
        if self.query(".tool-diff"):
            self.query_one(".tool-diff", CJKStatic).update(content)
        else:
            await self.mount(CJKStatic(content, classes="tool-diff"))


class WorkingLine(Static):
    """输入框上方左侧的运行状态行：spinner 动画 + 状态标签 + 一句话。

    由 CliApp.set_working(state) 驱动：state 是 STATES 的键，None 时内容隐藏但保留占位。
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
        visibility: hidden;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self.state: str | None = None
        self._spinner: Spinner | None = None

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
        self.styles.visibility = "visible"
        self._advance()

    def hide(self) -> None:
        if self.state is None:
            return
        self.state = None
        self._spinner = None
        self.update("")
        self.styles.visibility = "hidden"

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
        color: ansi_bright_black;
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
