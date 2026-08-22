"""第 6 步：给 AI 消息加上「思考过程」行（Thinking）。

学到什么：
- 一个组件里可以有多行结构：AssistantMessage 现在是两行 ——
  thinking-row（灰点 + 思考内容）和 answer-row（白点 + Markdown 回答）。
- 同一个流式技巧用两次：先把思考内容逐字写出来，再流式输出回答。
- thinking-row 和 answer-row 初始带 `stream-pending`（`display: none`）：
  每一行都等自己的首个字符到达才显示，所以不会提前出现空的 `●`。
- 用 Text 的 style 参数控制颜色 + 斜体，让思考内容看起来「轻」一点。

和第 5 步的区别：回答之前，先有一行灰色斜体的思考过程。
"""

import asyncio
from typing import Any, cast

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import HorizontalGroup, Vertical, VerticalScroll
from textual.reactive import Reactive, ReactiveType
from textual.widget import Widget
from textual.widgets import Input, Markdown, Static

from .cjk_wrap import CJKStatic

THINKING = "Simple greeting, respond in Chinese."

ANSWER = """\
这是 **Markdown** 渲染的回答：

- 支持列表
- 支持 `行内代码`

```python
print('Hello, Textual!')
```
"""


class UserMessage(CJKStatic):
    """用户消息：✨ 黄色前缀。"""

    DEFAULT_CSS = """
    UserMessage {
        width: 1fr;
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(self, text: str, **kwargs: Any) -> None:
        content = Text.assemble(("✨ ", "yellow"), (text, ""))
        super().__init__(content, **kwargs)


class AssistantMessage(Vertical):
    """AI 消息：第一行思考过程（灰点 + 灰斜体），第二行回答（白点 + Markdown）。"""

    DEFAULT_CSS = """
    AssistantMessage {
        width: 1fr;
        height: auto;
    }
    AssistantMessage .stream-pending {
        display: none;
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
    """

    def compose(self) -> ComposeResult:
        # 第一行：思考过程
        with HorizontalGroup(classes="thinking-row stream-pending"):
            yield Static("●", classes="thinking-bullet")
            yield CJKStatic("", id="thinking-content")
        # 第二行：回答
        with HorizontalGroup(classes="answer-row stream-pending"):
            yield Static("●", classes="assistant-bullet")
            yield Markdown(id="answer-md")



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
        padding: 1 2;
    }
    #user-input {
        dock: bottom;
        height: auto;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with ChatScroll(id="chat-scroll"):
            pass
        yield Input(placeholder="输入问题，按 Enter 发送", id="user-input")

    def on_mount(self) -> None:
        """启动后自动聚焦输入框。"""
        self.query_one("#user-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value.strip()
        if not user_text:
            return

        self.query_one("#user-input", Input).value = ""

        scroll = self.query_one("#chat-scroll", VerticalScroll)
        await scroll.mount(UserMessage(user_text))
        message = AssistantMessage()
        await scroll.mount(message)

        scroll.anchor()

        self.run_worker(self.stream_response(message))

    async def stream_response(self, message: AssistantMessage) -> None:
        """先逐字写出思考过程，再流式输出回答。"""
        # 第一步：思考内容逐字出现（每 0.02 秒一个字）
        thinking_content = message.query_one("#thinking-content", Static)
        thinking_row = message.query_one(".thinking-row")
        buffer = ""
        for char in THINKING:
            if not buffer:
                thinking_row.remove_class("stream-pending")
            buffer += char
            thinking_content.update(buffer)
            await asyncio.sleep(0.02)

        # 第二步：回答流式输出
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
