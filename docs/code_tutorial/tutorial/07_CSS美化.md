# 第 07 章：CSS 美化与中文换行修复（steps/step07_styling.py）

## 本步目标

上一章界面已经能聊，但长相还是「Textual 默认皮」。这一章**逻辑一行不改，全是长相**：启动后顶部出现一个蓝色圆角欢迎框（logo + 欢迎语 + Directory/Session/Model/Version 信息行），底部输入框变成带圆角边框的 `> ` 提示符样式，消息之间的间距用 `margin` 调得松紧合适，回答换成真实感的两段中文。另外，从这一步起 Markdown 回答改用 `CJKMarkdown`，修复中文长段落「提前换行、右侧留白」的问题。

## 新概念

- **`border: round 颜色`**：Textual CSS 的边框声明，`round` 是圆角样式，后面跟颜色。边框可以画在任何 Widget 上——包括容器。这一步的欢迎框和输入框边框都是画在容器上的。
- **「容器画边框，Input 去边框」的组合手法**：`Input` 自带一个默认边框，直接放进来会是「框中框」。做法是外层用一个 `Horizontal` 容器画圆角边框，里面放一个 `> ` 提示符文字和一个 `border: none` 的 `Input`，视觉上就是一个整体输入框。真实 CLI（Claude Code、Kimi Code）的输入框都是这么拼出来的。
- **`margin` 四个值**：`margin: 上 右 下 左`，控制组件和邻居之间的空隙。这一步用它精确控制「用户消息和上面空一行、AI 消息和下面空一行」的节奏。
- **`MarkdownParagraph:last-child` 选择器**：Markdown 组件内部，每个段落是一个 `MarkdownParagraph` 子组件，段落之间默认有下 margin。`:last-child` 选中最后一个段落，把它的 `margin-bottom` 清零，否则每条 AI 消息尾巴上会多出一个空行。
- **CJK 换行修复（`steps/cjk_wrap.py`）**：Textual 的文本换行底层走 Rich 的 `divide_line()`，它只认空格分词。一段没有空格的中文会被当成「一个超长的词」，只要这个词比整行窄，就被整体挪到下一行——于是中文段落写了一半就换行，右侧空一大片。`steps/cjk_wrap.py` 里的 `cjk_divide_line()` 自己算断行（CJK 宽字符之间随时可断），再用一个 `Visual` 包装层（`CJKContentVisual`）把预断行后的内容交回原生渲染流程。对外暴露两个可直接替换的组件：`CJKMarkdown`（替换 `Markdown`）和 `CJKStatic`（替换 `Static`）。不需要改 Textual 源码。

## 动手实现

在上一章 `steps/step06_thinking.py` 的基础上改。新增和改动共五块。

### 1. 导入与常量

在上一版的导入里加上 `Path`、`Horizontal`，并从 `cjk_wrap` 多导入一个 `CJKMarkdown`（上一章已经导入了 `CJKStatic`）：

```python
import asyncio
from pathlib import Path

from rich.text import Text

from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.containers import Horizontal, HorizontalGroup, Vertical, VerticalScroll
from textual.widgets import Input, Markdown, Static

from cjk_wrap import CJKMarkdown, CJKStatic
```

文件顶部加几个界面文案常量（`steps/step07_styling.py:29-39`）。`ANSWER` 从上一章的 Markdown 语法演示换成两段真实感的中文回答——这也顺带当 CJK 换行的测试素材：

```python
THINKING = "Simple greeting, respond in Chinese."

ANSWER = (
    "你好！有什么我可以帮你的吗？\n\n"
    "从工作目录看，这是一个 Textual 框架的 Claude Code 风格聊天应用教程项目"
    "（step01 到 step12）。需要继续开发、调试或讲解哪一部分，直接告诉我即可。"
)

MODEL_NAME = "K3-256k"
APP_VERSION = "0.34.0"
ACCENT = "#4a9eff"
```

### 2. 新增 WelcomeBox 组件

这是本步最大的新组件（`steps/step07_styling.py:42-86`），一个 `Vertical` 容器，里面三样东西：色块 logo、两行欢迎文字、四行信息。

```python
class WelcomeBox(Vertical):
    """顶部欢迎信息框：蓝色圆角边框 + logo + 欢迎语 + 信息行。"""

    DEFAULT_CSS = """
    WelcomeBox {
        width: 1fr;
        height: auto;
        background: transparent;
        border: round #4a9eff;   /* 圆角蓝色边框，整个框的气质就靠它 */
        padding: 1 2;
        margin: 1 1 0 1;
    }
    WelcomeBox .logo {
        width: 7;
        height: 2;
        background: #4a9eff;     /* 色块当 logo：蓝底深字 */
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
        with HorizontalGroup():                       # logo 和欢迎语横排
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
```

几个细节：

- logo 不是图片，就是一个 `Static` 写上 `" ▪  ▪ "`，再用 CSS 给它蓝色背景、7 格宽 2 行高——终端 UI 里的「图形」基本都是字符加背景色拼的。
- 信息行用 `Text.assemble` 把「标签灰、内容亮灰」两段颜色拼在一起，标签后面的空格是对齐用的。
- 横排用 `HorizontalGroup` 而不是 `Horizontal`：`Horizontal` 默认 `height: 1fr`，会把父容器撑满整屏；`HorizontalGroup` 是自动高度，只占了需要的行数。

### 3. 给消息组件补 margin

`UserMessage` 的 CSS 只改一行（`steps/step07_styling.py:92-98`）：把上一版的 `margin-top: 1` 改成 `margin: 1 1 0 1`，即「上面空一行、左右各缩一格、下面不空」。

`AssistantMessage` 的 CSS 改动较多（`steps/step07_styling.py:108-155`），挑关键的三处说：

```css
AssistantMessage {
    width: 1fr;
    height: auto;
    margin: 0 1 1 1;          /* 上面不空（用户消息已空过）、下面空一行 */
}
```

```css
AssistantMessage .thinking-row {
    width: 1fr;
    height: auto;
    margin-top: 1;            /* thinking 行和上面拉开一行 */
}
```

上一版 thinking 行和回答行没有自己的 margin，几行挤在一起。这一版给两行各加 `margin-top: 1`，消息内部也有了呼吸感。

最后是去尾巴空行的关键规则：

```css
/* 最后一个段落的下 margin 去掉，不然消息尾巴多一行空行 */
AssistantMessage MarkdownParagraph:last-child {
    margin-bottom: 0;
}
```

`ANSWER` 是两段文字，Markdown 内部就是两个 `MarkdownParagraph`，默认第二个段落下面还有 margin，叠上 `AssistantMessage` 自己的 `margin-bottom: 1` 就空太多了，所以清掉。

### 4. 回答行换成 CJKMarkdown

在 `AssistantMessage.compose` 里（`steps/step07_styling.py:157-163`），把上一版的 `Markdown(id="answer-md")` 改成 `CJKMarkdown(id="answer-md")`：

```python
def compose(self) -> ComposeResult:
    with HorizontalGroup(classes="thinking-row stream-pending"):
        yield Static("●", classes="thinking-bullet")
        yield CJKStatic("", id="thinking-content")
    with HorizontalGroup(classes="answer-row stream-pending"):
        yield Static("●", classes="assistant-bullet")
        yield CJKMarkdown(id="answer-md")   # 上一版是 Markdown
```

就这一个词的变化。`CJKMarkdown` 继承自 `Markdown`，接口完全一样（`get_stream`、`source` 都能照常用），只是段落块的换行规则换成了 CJK 友好的那一套。上一章我们已经把 `UserMessage` 和 thinking 内容换成了 `CJKStatic`，到这一步三类文字（用户消息、thinking、Markdown 回答）就全部用上 CJK 换行了。

### 5. App 层：欢迎框进滚动区，输入框换装

App 的 CSS（`steps/step07_styling.py:187-221`）里，输入区域从「一个裸 `Input` 钉在底部」变成三层结构：

```css
/* 输入区域：底部停靠，外层容器画边框 */
#input-area {
    dock: bottom;
    width: 1fr;
    height: auto;
}
#input-row {
    width: 1fr;
    height: 3;                 /* 圆角边框占上下两行，内容一行 */
    border: round #3a3f4a;     /* 边框画在容器上 */
    padding: 0 1;
    margin: 1 1 0 1;
}
#prompt {
    width: auto;               /* Static 默认 1fr，不改成 auto 会挤掉 Input */
    height: auto;
    color: ansi_default;
    padding-right: 1;
}
#user-input {
    width: 1fr;
    height: auto;
    border: none;              /* Input 自己的边框关掉，不然框中框 */
    padding: 0;
}
```

`compose` 相应改成（`steps/step07_styling.py:223-229`）：`WelcomeBox` 挂在滚动区里（这样消息多了它会跟着往上滚走，和真实 CLI 一样），输入区变成 `input-area > input-row > (prompt + Input)`：

```python
def compose(self) -> ComposeResult:
    with ChatScroll(id="chat-scroll"):
        yield WelcomeBox()                      # 新增：欢迎框在滚动区顶部
    with Vertical(id="input-area"):
        with Horizontal(id="input-row"):
            yield Static(">", id="prompt")
            yield Input(placeholder="", id="user-input")
```

`on_mount`、`on_input_submitted`、`stream_response` 三个方法和上一章完全一样，不用动。

## 完整代码

也可以直接运行仓库里的 `steps/step07_styling.py` 对照。

```python
"""第 7 步：用 CSS 把界面「打扮」成 Kimi Code 的样子。

学到什么：
- WelcomeBox：顶部欢迎框 —— 圆角蓝色边框（border: round）+ 色块 logo + 信息行。
- 输入框变身：外层 Horizontal 带圆角边框，里面放 "> " 提示符和「无边框」的 Input。
  边框画在容器上，Input 自己 border: none —— 这是「组合出好看输入框」的常用手法。
- margin 控制消息间距：用户消息上 margin、AI 消息下 margin，段落尾巴用
  MarkdownParagraph:last-child 去掉，不然两条消息之间会多空一行。
- 回答换成真实感的两段中文，顺带演示 Markdown 段间距。
- 中文长段落会「提前换行、右侧留白」：这一步起 Markdown 换成了 cjk_wrap.py
  里的 CJKMarkdown（原理见该文件头部注释和 README「踩过的坑」）。

和第 6 步的区别：逻辑没变，全是「长相」变了。
"""

import asyncio
from pathlib import Path

from rich.text import Text

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
    """AI 消息：thinking 行 + 回答行，行间距用 margin 调。"""

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
    /* 最后一个段落的下 margin 去掉，不然消息尾巴多一行空行 */
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
    /* 输入区域：底部停靠，外层容器画边框 */
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
    """

    def compose(self) -> ComposeResult:
        with ChatScroll(id="chat-scroll"):
            yield WelcomeBox()
        with Vertical(id="input-area"):
            with Horizontal(id="input-row"):
                yield Static(">", id="prompt")
                yield Input(placeholder="", id="user-input")

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
```

## 运行与验证

确保已按第 01 章装好环境，然后：

```bash
python steps/step07_styling.py
```

启动后应该看到：顶部蓝色圆角欢迎框（色块 logo、「Welcome to Kimi Code!」、四行信息），底部一个灰色圆角边框的输入框，里面是 `> ` 提示符。

可以这样戳一戳验证：

- 发一条消息，看 thinking 行（灰点斜体）先逐字出现，然后两段中文回答流式蹦出来；把终端窗口拉窄，观察中文段落是不是「撑满整行才换行」——如果换回普通 `Markdown`，会看到每行写了一半就换行、右侧大片空白。
- 连发三四条消息，看消息之间的间距是否均匀（用户消息和 AI 回答之间一行空隙），AI 消息尾巴上没有多余的空行。
- 消息多到超过一屏时，欢迎框应该跟着内容一起往上滚走，而不是钉在顶部。

手动验证时可以对照检查四件事：

- `WelcomeBox` 出现在滚动区里、含 Welcome 文字，且确实有蓝色边框（不是纯文字）；
- `#input-row` 有边框而输入框 `#user-input` 自身无边框——边框画在容器上这条手法成立；
- 发消息后两段中文回答完整流式到达，和「完整代码」里的 `ANSWER` 一致，说明换组件不影响原有流程。

（如果环境变量里有 `NO_COLOR=1`，Textual 会进入灰度模式，颜色观感会受影响，手动运行时建议用 `env -u NO_COLOR python steps/step07_styling.py`；PowerShell 则先 `$env:NO_COLOR=""`。）

## 常见问题

- **中文段落提前换行、右侧一大片空白**：不是 CSS 问题，是 Rich 的 `divide_line()` 按空格分词，把没空格的中文当成一个超长的词整体挪到下一行。解法就是用本步的 `CJKMarkdown` / `CJKStatic`（原理见 `steps/cjk_wrap.py` 头部注释）。想直观对比，可以把 `CJKMarkdown` 临时换回普通 `Markdown` 再发一条消息，会看到每行写一半就换行、右侧留白。
- **横排的 `Static` 把后面的组件挤没了**：`Static` 默认 `width: 1fr`，在水平排列里会吃掉所有剩余宽度。凡是横排里的小元素（圆点、`> ` 提示符）都要像本步这样写 `width: auto`。
- **AI 消息尾巴多一个空行**：Markdown 每个段落默认有下 margin，最后一个段落的 margin 会叠在组件自己的 margin 上。本步用 `MarkdownParagraph:last-child { margin-bottom: 0; }` 清掉；漏了这条，两段式回答后面就会多空一行。
