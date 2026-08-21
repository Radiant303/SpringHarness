"""第 8 步：输入框记住历史命令，按 ↑↓ 翻（像终端一样）。

学到什么：
- 继承 Input 做 HistoryInput：自己存一个 _history 列表。
- on_key 事件：按 ↑ 往上翻历史、按 ↓ 往下翻，翻到底回到「草稿」。
  记得 event.stop()，不然按键还会继续传给别的组件。
- 翻历史前先把当前正在输入的内容存成 _draft，翻回来时不丢。

和第 7 步的区别：输入框换成 HistoryInput，能按 ↑ 找回上次发的话。
"""

import asyncio
from pathlib import Path

from rich.text import Text

from textual import events
from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.containers import Horizontal, HorizontalGroup, Vertical, VerticalScroll
from textual.widgets import Input, Markdown, Static

from cjk_wrap import CJKMarkdown, CJKStatic


THINKING = "Simple greeting, respond in Chinese."

ANSWER = (
    "你好！有什么我可以帮你的吗？\n\n"
    "从工作目录看，这是一个 Textual 框架的 Claude Code 风格聊天应用教程项目"
    "（step01 到 step12）。需要继续开发、调试或讲解哪一部分，直接告诉我即可。"
)

MODEL_NAME = "K3-256k"
APP_VERSION = "0.34.0"
ACCENT = "#4a9eff"


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

    def __init__(self, text: str, **kwargs) -> None:
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
        color: #c8cdd5;
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


class HistoryInput(Input):
    """带上下历史记忆的输入框。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        # 当前翻到历史的第几条；None 表示没在翻历史（正在编辑新内容）
        self._history_pos: int | None = None
        # 开始翻历史之前，输入框里的内容（草稿）
        self._draft: str = ""

    async def on_key(self, event: events.Key) -> None:
        if event.key == "up":
            event.stop()  # 阻止按键继续传播（比如被滚动区当成滚屏）
            self._history_previous()
        elif event.key == "down":
            event.stop()
            self._history_next()
        else:
            # 用户开始打字了，就退出「翻历史」状态
            self._history_pos = None

    def _history_previous(self) -> None:
        """↑ ：往更早的历史翻。"""
        if not self._history:
            return
        if self._history_pos is None:
            # 第一次按 ↑：先保存草稿，再跳到最新一条历史
            self._draft = self.value
            self._history_pos = len(self._history) - 1
        elif self._history_pos > 0:
            self._history_pos -= 1
        self.value = self._history[self._history_pos]

    def _history_next(self) -> None:
        """↓ ：往更近的历史翻，翻过头就恢复草稿。"""
        if self._history_pos is None:
            return
        self._history_pos += 1
        if self._history_pos >= len(self._history):
            self._history_pos = None
            self.value = self._draft
        else:
            self.value = self._history[self._history_pos]

    def push_history(self, text: str) -> None:
        """发送成功后，把这条内容记入历史。"""
        if text:
            self._history.append(text)
        self._history_pos = None
        self._draft = ""



class ChatScroll(VerticalScroll):
    """聊天滚动区：修复 anchor() 的一个小 bug。

    anchor() 让滚动区一直吸底；但 Textual 的合成器在「内容不足一屏」时
    会把 scroll_y 直接设成负数（set_reactive 绕过了 0 下限的校验），表现为：
    第一次发消息后，上面的内容整体往下挪、顶部空出一片。
    这里把负的滚动值挡回去即可。
    """

    def set_reactive(self, reactive, value) -> None:
        if (
            isinstance(value, (int, float))
            and value < 0
            and (reactive is Widget.scroll_y or reactive is Widget.scroll_target_y)
        ):
            value = 0
        super().set_reactive(reactive, value)


class ChatApp(App):
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
        color: #c8cdd5;
        padding-right: 1;
    }
    #user-input {
        width: 1fr;
        height: auto;
        border: none;
        padding: 0;
    }
    """

    def compose(self) -> ComposeResult:
        with ChatScroll(id="chat-scroll"):
            yield WelcomeBox()
        with Vertical(id="input-area"):
            with Horizontal(id="input-row"):
                yield Static(">", id="prompt")
                # 唯一的区别：这里从 Input 换成了 HistoryInput
                yield HistoryInput(placeholder="", id="user-input")

    def on_mount(self) -> None:
        """启动后自动聚焦输入框。"""
        self.query_one("#user-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value.strip()
        if not user_text:
            return

        input_widget = self.query_one("#user-input", HistoryInput)
        input_widget.value = ""
        input_widget.push_history(user_text)  # 记入历史

        scroll = self.query_one("#chat-scroll", VerticalScroll)
        await scroll.mount(UserMessage(user_text))
        message = AssistantMessage()
        await scroll.mount(message)

        scroll.anchor()

        self.run_worker(self.stream_response(message))

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
