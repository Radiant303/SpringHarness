"""第 2 步：消息多到超出屏幕后，让滚动区自动跟着新消息滚到底。

学到什么：
- scroll_end(animate=False)：一次性滚到底部（第 1 步用的就是它）。
- anchor()：「锚定」底部——之后每次有新消息进来都会自动跟着滚；
  用户手动上翻时锚定会自动解除，不打断阅读，回到底部附近又重新锚定。
- ChatScroll：anchor() 有个小 bug——内容不足一屏时，框架会把滚动位置
  设成负数（内容整体下移、顶部空白）。这个子类把负值挡回去。
  后面每一步的滚动区都用它。

和第 1 步的区别：scroll_end 换成 anchor，滚动区换成 ChatScroll。
"""

from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.containers import VerticalScroll
from textual.widgets import Input, Static


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
        await scroll.mount(Static(f"你: {user_text}"))
        await scroll.mount(Static("AI: 收到！"))

        # 锚定到底部：新消息进来时自动跟随滚动
        scroll.anchor()


if __name__ == "__main__":
    app = ChatApp()
    app.run()
