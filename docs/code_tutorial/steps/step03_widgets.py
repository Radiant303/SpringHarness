"""第 3 步：把消息做成自定义组件，加上 ✨ / ● 前缀和颜色。

学到什么：
- 继承 Static 写自己的组件（UserMessage / AssistantMessage）。
- DEFAULT_CSS：组件自带的样式，跟着组件走。
- Rich 的 Text.assemble：给同一段文字的不同部分上不同颜色。

和第 2 步的区别：消息不再是光秃秃的 Static 字符串，
而是有样式、有前缀图标的自定义组件。
"""

from typing import Any, cast

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import Reactive, ReactiveType
from textual.widget import Widget
from textual.widgets import Input, Static

from .cjk_wrap import CJKStatic


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
        # Text.assemble 把多段（文字, 样式）拼成一段富文本
        content = Text.assemble(("✨ ", "yellow"), (text, ""))
        super().__init__(content, **kwargs)


class AssistantMessage(Static):
    """AI 消息：● 圆点前缀（这一步还是一条固定回复）。"""

    DEFAULT_CSS = """
    AssistantMessage {
        width: 1fr;
        height: auto;
    }
    """

    def __init__(self, text: str, **kwargs: Any) -> None:
        content = Text.assemble(("● ", "#c8cdd5"), (text, ""))
        super().__init__(content, **kwargs)



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
        await scroll.mount(AssistantMessage("收到！这就是自定义消息组件。"))

        scroll.anchor()


if __name__ == "__main__":
    app = ChatApp()
    app.run()
