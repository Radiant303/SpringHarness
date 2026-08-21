"""第 1 步：最小可运行的聊天界面。

学到什么：
- App 和 compose()：界面由一个个组件（Widget）组成。
- VerticalScroll：可滚动的容器，用来放聊天记录。
- Input：底部输入框。
- on_input_submitted：按下回车触发的事件。
- mount()：把新消息组件挂到滚动区里。
- query_one()：按 id 找到某个组件。
- on_mount()：启动后做一件事——把焦点放到输入框上。
  （不聚焦的话，按键会被可滚动的聊天区抢走，打字没反应。）
"""

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Static


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
        # 可滚动的聊天记录区（现在是空的，消息以后动态加进去）
        with VerticalScroll(id="chat-scroll"):
            pass
        # 底部输入框
        yield Input(placeholder="输入问题，按 Enter 发送", id="user-input")

    def on_mount(self) -> None:
        """启动后自动聚焦输入框，这样一打开就能直接打字。"""
        self.query_one("#user-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """用户按下回车时触发。"""
        user_text = event.value.strip()
        if not user_text:
            return

        # 清空输入框
        self.query_one("#user-input", Input).value = ""

        # 把用户消息和一条固定的 AI 回复挂到滚动区
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        await scroll.mount(Static(f"你: {user_text}"))
        await scroll.mount(Static("AI: 收到！"))

        # 滚动到底部，让新消息可见
        scroll.scroll_end(animate=False)


if __name__ == "__main__":
    app = ChatApp()
    app.run()
