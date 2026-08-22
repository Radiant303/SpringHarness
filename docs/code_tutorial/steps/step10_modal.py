"""第 10 步：/model 弹出一个「模型选择」模态窗口。

学到什么：
- ModalScreen：盖在主界面上面的一层「屏幕」，Esc 关闭（BINDINGS + dismiss）。
- push_screen()：把 ModalScreen 推上去；主界面还在下面，只是被盖住。
- 弹窗本身也是一个组件树：标题、帮助、警告、provider 标签、模型列表，全是 Static 组合。

和第 9 步的区别：/model 命令不再只是打一行提示，而是真的弹窗。
"""

import asyncio
from pathlib import Path
from typing import Any, ClassVar, cast

from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, HorizontalGroup, Vertical, VerticalScroll
from textual.reactive import Reactive, ReactiveType
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Markdown, Static

from .cjk_wrap import CJKMarkdown, CJKStatic

THINKING = "Simple greeting, respond in Chinese."

ANSWER = (
    "你好！有什么我可以帮你的吗？\n\n"
    "从工作目录看，这是一个 Textual 框架的 Claude Code 风格聊天应用教程项目"
    "（step01 到 step12）。需要继续开发、调试或讲解哪一部分，直接告诉我即可。"
)

MODEL_NAME = "K3-256k"
APP_VERSION = "0.34.0"
ACCENT = "#4a9eff"

COMMANDS = [
    ("yolo", "Toggle YOLO mode: auto-approve tool actions."),
    ("model", "Switch LLM model"),
    ("permission", "Select permission mode"),
    ("plan", "Toggle plan mode"),
    ("settings", "Open TUI settings"),
]


class WelcomeBox(Vertical):
    """顶部欢迎信息框：蓝色圆角边框 + logo + 欢迎语 + 信息行。"""

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
    }
    WelcomeBox .info {
        width: 1fr;
        height: auto;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        cwd = Path.cwd()
        with HorizontalGroup():
            yield Static(" ▪  ▪ ", classes="logo")
            with Vertical(classes="welcome-text"):
                yield Static(Text("Welcome to Kimi Code!", style=f"bold {ACCENT}"))
                yield Static(Text("Send /help for help information.", style="#7a8391"))
        yield Static(
            Text.assemble(
                ("Directory: ", "#7a8391"), (f"{cwd}\n", "#9aa3b0"),
                ("Session:   ", "#7a8391"), ("session_xxx\n", "#9aa3b0"),
                ("Model:     ", "#7a8391"), (f"{MODEL_NAME}\n", "#9aa3b0"),
                ("Version:   ", "#7a8391"), (APP_VERSION, "#9aa3b0"),
            ),
            classes="info",
        )


class UserMessage(CJKStatic):
    """用户消息：✨ 黄色前缀。"""

    DEFAULT_CSS = """
    UserMessage {
        width: 1fr;
        height: auto;
        margin: 1 1 0 1;
    }
    """

    def __init__(self, text: str, **kwargs: Any) -> None:
        content = Text.assemble(("✨ ", "yellow"), (text, ""))
        super().__init__(content, **kwargs)


class AssistantMessage(Vertical):
    """AI 消息：thinking 行 + 回答行。"""

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
            yield CJKStatic("", id="thinking-content")
        with HorizontalGroup(classes="answer-row stream-pending"):
            yield Static("●", classes="assistant-bullet")
            yield CJKMarkdown(id="answer-md")


class CommandDropdown(Vertical):
    """命令下拉框，出现在输入框上方。"""

    DEFAULT_CSS = """
    CommandDropdown {
        width: 1fr;
        height: auto;
        max-height: 8;
        background: transparent;
        border: round #4a9eff;
        margin: 0 1;
        display: none;
    }
    CommandDropdown .command-option {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    CommandDropdown .command-name {
        width: 20;
        color: #4a9eff;
    }
    CommandDropdown .command-desc {
        width: 1fr;
        color: #7a8391;
    }
    CommandDropdown .selected .command-name {
        color: #ffffff;
        text-style: bold;
    }
    CommandDropdown .dropdown-count {
        width: 1fr;
        color: #7a8391;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._commands: list[tuple[str, str]] = COMMANDS
        self._filtered: list[tuple[str, str]] = self._commands
        self._selected_index = 0
        self._rendered_names: list[str] = []
        self.visible = False

    def compose(self) -> ComposeResult:
        return []

    async def show(self) -> None:
        self.visible = True
        self.display = True
        await self._render_list()

    def hide(self) -> None:
        self.visible = False
        self.display = False

    def filter(self, query: str) -> None:
        if not query.startswith("/"):
            self.hide()
            return
        query = query[1:].lower()
        self._filtered = [
            (name, desc)
            for name, desc in self._commands
            if name.startswith(query)
        ]
        self._selected_index = 0
        if self._filtered:
            self.app.run_worker(self.show())
        else:
            self.hide()

    async def _render_list(self) -> None:
        """列表内容没变时只更新选中态，避免销毁重建导致闪烁。"""
        names = [name for name, _ in self._filtered[:5]]
        if names == self._rendered_names and self.children:
            self._update_selection()
            return
        await self.remove_children()
        rows: list[Widget] = [
            HorizontalGroup(
                Static(
                    f"{'→ ' if idx == self._selected_index else '  '}{name}",
                    classes="command-name",
                ),
                Static(desc, classes="command-desc"),
                classes="command-option selected" if idx == self._selected_index else "command-option",
            )
            for idx, (name, desc) in enumerate(self._filtered[:5])
        ]
        rows.append(
            Static(f"  ({len(self._filtered)}/{len(self._commands)})", classes="dropdown-count")
        )
        await self.mount_all(rows)
        self._rendered_names = names

    def _update_selection(self) -> None:
        for idx, row in enumerate(self.query(".command-option")):
            selected = idx == self._selected_index
            row.set_class(selected, "selected")
            name = self._filtered[idx][0]
            arrow = "→ " if selected else "  "
            row.query_one(".command-name", Static).update(f"{arrow}{name}")

    def move_up(self) -> None:
        if self._selected_index > 0:
            self._selected_index -= 1
            self._update_selection()

    def move_down(self) -> None:
        if self._selected_index < len(self._filtered) - 1:
            self._selected_index += 1
            self._update_selection()

    def select_current(self) -> str | None:
        if 0 <= self._selected_index < len(self._filtered):
            return self._filtered[self._selected_index][0]
        return None


class HistoryInput(Input):
    """带历史记忆的输入框；下拉框可见时，↑↓/Enter/Esc 优先给下拉框。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        self._history_pos: int | None = None
        self._draft: str = ""

    async def on_key(self, event: events.Key) -> None:
        dropdown = self.app.query_one("#command-dropdown", CommandDropdown)

        if dropdown.visible:
            if event.key == "up":
                event.stop()
                dropdown.move_up()
                return
            elif event.key == "down":
                event.stop()
                dropdown.move_down()
                return
            elif event.key == "enter":
                event.stop()
                selected = dropdown.select_current()
                if selected is not None:
                    self.value = f"/{selected}"
                    dropdown.hide()
                    self.post_message(Input.Submitted(self, self.value))
                return
            elif event.key == "escape":
                event.stop()
                dropdown.hide()
                return

        if event.key == "up":
            event.stop()
            self._history_previous()
        elif event.key == "down":
            event.stop()
            self._history_next()
        else:
            self._history_pos = None

    def _history_previous(self) -> None:
        if not self._history:
            return
        if self._history_pos is None:
            self._draft = self.value
            self._history_pos = len(self._history) - 1
        elif self._history_pos > 0:
            self._history_pos -= 1
        self.value = self._history[self._history_pos]

    def _history_next(self) -> None:
        if self._history_pos is None:
            return
        self._history_pos += 1
        if self._history_pos >= len(self._history):
            self._history_pos = None
            self.value = self._draft
        else:
            self.value = self._history[self._history_pos]

    def push_history(self, text: str) -> None:
        if text:
            self._history.append(text)
        self._history_pos = None
        self._draft = ""


class ModelSelectScreen(ModalScreen[None]):
    """模型选择弹窗（简化版：只展示，不真正切换）。"""

    CSS = """
    ModelSelectScreen {
        align: center middle;
    }
    #model-dialog {
        width: 70;
        height: auto;
        background: transparent;
        border: round #4a9eff;
        padding: 1 2;
    }
    #model-title {
        color: #4a9eff;
        text-style: bold;
        margin-bottom: 1;
    }
    #model-help {
        color: #7a8391;
        margin-bottom: 1;
    }
    #model-warning {
        color: #e5c07b;
        margin-bottom: 1;
    }
    #provider-tabs {
        height: auto;
        margin-bottom: 1;
    }
    .provider-tab {
        width: auto;
        padding: 0 2;
        background: transparent;
        color: #7a8391;
    }
    .provider-tab.-active {
        background: #4a9eff;
        color: #ffffff;
        text-style: bold;
    }
    #model-list {
        height: auto;
        max-height: 10;
    }
    #model-list .model-name {
        width: 24;
        color: ansi_default;
    }
    #model-list .model-current {
        color: #4a9eff;
    }
    #model-list .model-provider {
        color: #7a8391;
    }
    #thinking-section {
        height: auto;
        margin-top: 1;
        color: ansi_default;
    }
    #thinking-section Static {
        width: auto;
    }
    """

    # 按 Esc 触发 action_cancel
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._models = [
            ("K2.7 Coding Highspeed", "Kimi Code"),
            ("K3", "Kimi Code"),
            ("K3-256k", "Kimi Code"),
        ]
        self._current_model = "K3-256k"

    def compose(self) -> ComposeResult:
        with Vertical(id="model-dialog"):
            yield Static("Select a model  (type to search)", id="model-title")
            yield Static(
                "Tab toggle provider · ↑↓ navigate · Enter select · Esc cancel",
                id="model-help",
            )
            yield Static(
                "Note: Switching models invalidates the existing prompt cache.",
                id="model-warning",
            )

            with Horizontal(id="provider-tabs"):
                yield Static(" All ", classes="provider-tab -active")
                yield Static(" ruoli ", classes="provider-tab")
                yield Static(" deepseek ", classes="provider-tab")

            with Vertical(id="model-list"):
                for name, provider in self._models:
                    is_current = name == self._current_model
                    name_text = f"> {name}" if is_current else f"  {name}"
                    name_classes = "model-name model-current" if is_current else "model-name"
                    provider_text = f"{provider} ← current" if is_current else provider
                    yield HorizontalGroup(
                        Static(name_text, classes=name_classes),
                        Static(provider_text, classes="model-provider"),
                    )

            with Horizontal(id="thinking-section"):
                yield Static("Thinking  (←→ to switch)   ")
                yield Static(" Low   ")
                yield Static(Text("[ High ]", style=f"bold {ACCENT}"))
                yield Static("   Max")

    def action_cancel(self) -> None:
        """Esc 时关闭弹窗（dismiss 把弹窗从屏幕栈上拿掉）。"""
        self.dismiss(None)



class ChatScroll(VerticalScroll):
    """聊天滚动区：修复 anchor() 的一个小 bug。

    anchor() 让滚动区一直吸底；但 Textual 的合成器在「内容不足一屏」时
    会把 scroll_y 直接设成负数（set_reactive 绕过了 0 下限的校验），表现为：
    第一次发消息后，上面的内容整体往下挪、顶部空出一片。
    这里把负的滚动值挡回去即可。
    """

    def set_reactive(self, reactive: Reactive[ReactiveType], value: ReactiveType) -> None:
        if (
            isinstance(value, (int, float))
            and value < 0
            and (reactive is Widget.scroll_y or reactive is Widget.scroll_target_y)
        ):
            value = cast(ReactiveType, 0)
        super().set_reactive(reactive, value)


class ChatApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }
    #chat-scroll {
        width: 1fr;
        height: 1fr;
        padding: 0;
    }
    #input-area {
        dock: bottom;
        width: 1fr;
        height: auto;
    }
    #input-row {
        width: 1fr;
        height: 3;
        border: round #3a3f4a;
        padding: 0 1;
        margin: 1 1 0 1;
    }
    #prompt {
        width: auto;
        height: auto;
        color: ansi_default;
        padding-right: 1;
    }
    #user-input {
        width: 1fr;
        height: auto;
        border: none;
        padding: 0;
    }
    .tip-sub {
        width: 1fr;
        height: auto;
        margin: 0 1 0 1;
    }
    .warning {
        width: 1fr;
        height: auto;
        margin: 0 1 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with ChatScroll(id="chat-scroll"):
            yield WelcomeBox()
        with Vertical(id="input-area"):
            yield CommandDropdown(id="command-dropdown")
            with Horizontal(id="input-row"):
                yield Static(">", id="prompt")
                yield HistoryInput(placeholder="", id="user-input")

    def on_mount(self) -> None:
        """启动后自动聚焦输入框。"""
        self.query_one("#user-input", Input).focus()

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "user-input":
            return
        dropdown = self.query_one("#command-dropdown", CommandDropdown)
        dropdown.filter(event.value)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value.strip()

        input_widget = self.query_one("#user-input", HistoryInput)
        input_widget.value = ""
        input_widget.push_history(user_text)

        if not user_text:
            return

        if user_text.startswith("/"):
            await self.handle_command(user_text[1:])
            return

        scroll = self.query_one("#chat-scroll", VerticalScroll)
        await scroll.mount(UserMessage(user_text))
        message = AssistantMessage()
        await scroll.mount(message)

        scroll.anchor()

        self.run_worker(self.stream_response(message))

    async def handle_command(self, command: str) -> None:
        """处理斜杠命令：/model 弹窗，/help 打提示，未知命令打警告。"""
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        if command == "model":
            # 唯一的真正动作：把模态屏幕推上去
            self.push_screen(ModelSelectScreen())
        elif command == "help":
            names = " ".join(f"/{name}" for name, _ in COMMANDS) + " /help"
            await scroll.mount(
                Static(Text(f"  Available commands: {names}", style="#7a8391"), classes="tip-sub")
            )
            scroll.anchor()
        elif command in {name for name, _ in COMMANDS}:
            await scroll.mount(
                Static(Text(f"  命令 /{command} 已选中（演示）", style="#7a8391"), classes="tip-sub")
            )
            scroll.anchor()
        else:
            await scroll.mount(
                Static(Text(f"  Unknown command: /{command}", style="#e5c07b"), classes="warning")
            )
            scroll.anchor()

    async def stream_response(self, message: AssistantMessage) -> None:
        """先逐字写出思考过程，再流式输出回答。"""
        thinking_content = message.query_one("#thinking-content", Static)
        thinking_row = message.query_one(".thinking-row")
        buffer = ""
        for char in THINKING:
            if not buffer:
                thinking_row.remove_class("stream-pending")
            buffer += char
            thinking_content.update(buffer)
            await asyncio.sleep(0.02)

        md = message.query_one("#answer-md", Markdown)
        answer_row = message.query_one(".answer-row")
        stream = Markdown.get_stream(md)
        try:
            for i in range(0, len(ANSWER), 8):
                if i == 0:
                    answer_row.remove_class("stream-pending")
                await stream.write(ANSWER[i : i + 8])
                await asyncio.sleep(0.05)
        finally:
            await stream.stop()


if __name__ == "__main__":
    app = ChatApp()
    app.run()
