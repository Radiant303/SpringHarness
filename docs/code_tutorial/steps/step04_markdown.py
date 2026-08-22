"""第 4 步：AI 的回答用 Markdown 渲染（加粗、列表、代码块）。

学到什么：
- Markdown 组件：直接吃 Markdown 源文本，渲染成带格式的终端内容。
- AssistantMessage 从 Static 升级成 Vertical 容器：
  用 HorizontalGroup 把「● 圆点」和「Markdown 回答」横排在一起。
- HorizontalGroup：水平排列、高度自适应的容器（Horizontal 默认会撑满高度，这里不适用）。
- Markdown 默认有 `padding: 0 2`，要去掉，文字才能对齐在圆点后面。

和第 3 步的区别：AI 回复不再是纯文本 Static，而是 Markdown。
"""

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
    """AI 消息：● 圆点 + Markdown 回答。"""

    DEFAULT_CSS = """
    AssistantMessage {
        width: 1fr;
        height: auto;
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
        with HorizontalGroup(classes="answer-row"):
            yield Static("●", classes="assistant-bullet")
            yield Markdown(ANSWER, id="answer-md")



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
        await scroll.mount(AssistantMessage())

        scroll.anchor()


if __name__ == "__main__":
    app = ChatApp()
    app.run()
