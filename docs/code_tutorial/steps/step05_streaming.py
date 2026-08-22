"""第 5 步：让回答「一个字一个字往外蹦」—— 流式输出。

学到什么：
- Markdown 组件可以先创建为空白，再一点点往里写内容。
- Markdown.get_stream(md)：拿到一个「流写入器」，反复 write() 片段，
  它会自动合并刷新，不会把终端刷爆。
- run_worker()：把耗时的异步任务放到后台跑。
  为什么需要它？如果直接在 on_input_submitted 里 await 流式循环，
  在流结束之前，输入框的按键消息都排不上队，界面就「卡住」了。
- `.stream-pending { display: none; }`：回答首个 chunk 还没来时整行隐藏，
  避免先出现一个没有内容的孤立 `●`；首个 chunk 写入前再显示。

和第 4 步的区别：回答不再一次到位，而是分片流出来。
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
    """AI 消息：● 圆点 + Markdown 回答（初始为空白，等待流式写入）。"""

    DEFAULT_CSS = """
    AssistantMessage {
        width: 1fr;
        height: auto;
    }
    AssistantMessage .stream-pending {
        display: none;
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
        with HorizontalGroup(classes="answer-row stream-pending"):
            yield Static("●", classes="assistant-bullet")
            # 注意：这里不再传入 ANSWER，先创建一个空的 Markdown
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

        # 流式输出放到后台 worker 里跑，界面不会被卡住
        self.run_worker(self.stream_response(message))

    async def stream_response(self, message: AssistantMessage) -> None:
        """模拟 AI 的流式回答：每 0.05 秒吐出 8 个字符。"""
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
            # 不管中途是否出错，都要把流停掉，否则后台任务不会退出
            await stream.stop()


if __name__ == "__main__":
    app = ChatApp()
    app.run()
