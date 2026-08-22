# 第 04 章：回答用 Markdown 渲染

对应文件：`steps/step04_markdown.py`

## 本步目标

上一章 AI 的回答是一条纯文本 `Static`，没有任何格式。本章把它升级成真正的 Markdown 渲染：回答里可以有**加粗**、列表、`行内代码`、代码块，● 圆点和回答内容横排在同一行。视觉上开始接近真实的 CLI 助手了。

## 新概念

- **`Markdown` 组件**（`textual.widgets.Markdown`）：Textual 自带的组件，构造函数直接接收一段 Markdown 源文本，自动把标题、加粗、列表、代码块渲染成终端里的富文本。你不用自己解析 Markdown，给它字符串就行。
- **容器型自定义组件**：前三章的自定义组件都是「一段文字」，继承 `Static`。但一个自定义组件也可以继承容器（比如 `Vertical`），自己再写 `compose()` 往里面放子组件。本章的 `AssistantMessage` 就是这样一个「小组件拼出来的大组件」。
- **`HorizontalGroup`**：水平排列子组件、且高度随内容自适应的容器。为什么不用普通的 `Horizontal`？因为 `Horizontal` 默认 `height: 1fr`，会往高里撑满父容器；放在 `height: auto` 的消息里会把整行撑成整屏。`HorizontalGroup` 就是为「只占内容那么高」的场景准备的。
- **CSS 后代选择器**：`AssistantMessage .assistant-bullet` 表示「只作用于 `AssistantMessage` 内部的 `.assistant-bullet`」。组件自带样式时这么写，样式不会泄漏到界面上其他同名 class 的组件。

## 动手实现

在上一章 `steps/step03_widgets.py` 的基础上改。`UserMessage`、`ChatScroll`、`ChatApp` 的骨架完全不动，改动集中在 `AssistantMessage`。

### 1. 先准备一段 Markdown 回答

文件顶部加一个常量，模拟 AI 返回的回答（真实项目里这会是 LLM 的返回）：

````python
ANSWER = """\
这是 **Markdown** 渲染的回答：

- 支持列表
- 支持 `行内代码`

```python
print('Hello, Textual!')
```
"""
````

注意里面的代码块用的是三反引号，所以整个字符串用 `"""\` 开头（`\` 去掉第一个换行）。

### 2. 把 `AssistantMessage` 从 `Static` 升级成 `Vertical` 容器

上一章它是这样：继承 `Static`，在 `__init__` 里用 `Text.assemble` 拼「● + 文本」。现在回答是一段结构化的富文本，一个 `Static` 装不下了，改成容器组合：

```python
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
        color: ansi_default;
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
```

逐段看：

- `compose()` 里的 `with HorizontalGroup(...)`：`HorizontalGroup` 是容器，`with` 块里 `yield` 的组件都会成为它的子组件，横排成一行。这和 `ChatApp.compose()` 里 `with ChatScroll(...)` 的用法是同一套语法。
- `Static("●", classes="assistant-bullet")`：圆点。注意 CSS 里给了 `width: auto`——`Static` 默认 `width: 1fr`，在水平排列里会把后面的 Markdown 挤没，必须收窄成「内容多宽就多宽」。`padding: 0 1 0 0` 给圆点右边留一格空隙。
- `Markdown(ANSWER, id="answer-md")`：回答本体。CSS 里的 `padding: 0` 很关键——`Markdown` 默认自带 `padding: 0 2`（左右各缩进 2 格），不去掉的话回答文字会对不齐圆点，看着像缩进了。`background: transparent` 让它不要自己刷背景色，跟聊天区底色保持一致。
- 三条 CSS 都以 `AssistantMessage` 开头做限定，样式只影响 AI 消息内部。

### 3. 改发送逻辑：mount 时不再传文本

上一章 `on_input_submitted` 里是 `AssistantMessage("收到！这就是自定义消息组件。")`——内容从外面传进去。现在内容固定在组件内部（`compose` 里引用了 `ANSWER`），改成无参构造（`steps/step04_markdown.py:134`）：

```python
await scroll.mount(UserMessage(user_text))
await scroll.mount(AssistantMessage())
```

### 4. import 相应更新

顶部 import 加上 `HorizontalGroup`、`Vertical` 和 `Markdown`：

```python
from textual.containers import HorizontalGroup, Vertical, VerticalScroll
from textual.widgets import Input, Markdown, Static
```

就这些。`UserMessage`、`ChatScroll`、`ChatApp` 的 CSS 和事件处理和上一章一字不差。

## 完整代码

下面是 `steps/step04_markdown.py` 的完整源码，和仓库里的文件逐字一致。你也可以直接运行仓库里的文件对照。

````python
"""第 4 步：AI 的回答用 Markdown 渲染（加粗、列表、代码块）。

学到什么：
- Markdown 组件：直接吃 Markdown 源文本，渲染成带格式的终端内容。
- AssistantMessage 从 Static 升级成 Vertical 容器：
  用 HorizontalGroup 把「● 圆点」和「Markdown 回答」横排在一起。
- HorizontalGroup：水平排列、高度自适应的容器（Horizontal 默认会撑满高度，这里不适用）。
- Markdown 默认有 `padding: 0 2`，要去掉，文字才能对齐在圆点后面。

和第 3 步的区别：AI 回复不再是纯文本 Static，而是 Markdown。
"""

from rich.text import Text

from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.containers import HorizontalGroup, Vertical, VerticalScroll
from textual.widgets import Input, Markdown, Static

from cjk_wrap import CJKStatic


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

    def __init__(self, text: str, **kwargs) -> None:
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
        color: ansi_default;
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
        await scroll.mount(UserMessage(user_text))
        await scroll.mount(AssistantMessage())

        scroll.anchor()


if __name__ == "__main__":
    app = ChatApp()
    app.run()
````

## 运行与验证

确保已按第 01 章装好环境，然后：

```bash
python steps/step04_markdown.py
```

随便输入一句话回车，应该看到：

- 你的消息是 `✨` 黄色前缀，和上一章一样；
- 下面紧跟着 AI 消息：一个灰色 `●`，后面是渲染好的 Markdown——「Markdown」三个字加粗、两行列表、`行内代码` 有底色、代码块里的 `print(...)` 带语法高亮。

可以戳一戳验证：

- 连发多条消息，确认滚动区仍然自动吸底（`ChatScroll` 的修复还在生效）。
- 把终端窗口拉窄，看 Markdown 内容是否正常重排。

想再确认一步「回答确实由 Markdown 组件渲染，且内容没丢」，可以对照上面「完整代码」小节里 `ANSWER` 常量的源文本，逐个元素核对：加粗的「Markdown」、两行列表、`行内代码` 的底色、代码块的语法高亮，一样不少就说明内容完整走完了 Markdown 渲染管线。

## 常见问题

- **回答文字和圆点对不齐，整体缩进了两格**：忘了给 `Markdown` 写 `padding: 0`。`Markdown` 组件默认 `padding: 0 2`，左右各空两格，放在圆点后面会很明显。
- **用 `Horizontal` 代替 `HorizontalGroup`，消息行把屏幕撑满了**：`Horizontal`/`Vertical` 容器默认 `height: 1fr`，会尽量占满父容器的高度。放在 `height: auto` 的消息里需要自适应高度，必须用 `HorizontalGroup`。
- **圆点显示了，后面的回答被挤没 / 只剩窄窄一条**：水平排列里 `Static` 默认 `width: 1fr`，会抢光宽度。给 `.assistant-bullet` 加 `width: auto`，反过来给 `Markdown` 留 `width: 1fr` 占剩余空间。
- **`UserMessage` 继承的 `CJKStatic` 是什么**：它是 `steps/cjk_wrap.py` 里修过中文换行的 `Static`（中文长段落不会提前换行留白）。本步你把它当普通 `Static` 用即可，原理留到后面的章节再讲。
