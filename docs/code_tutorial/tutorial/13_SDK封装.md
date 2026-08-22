# 第 13 章：SDK 封装——几十行写出自己的 CLI（step13_sdk.py / steps/cli_ui/）

## 本步目标

前 12 章我们把一个 Claude Code / Kimi Code 风格的终端聊天界面一个零件一个零件地造了出来，成品是 749 行的 `step12_final.py`。但如果你想**用它**做点别的——比如给自己的 agent 套一个现成的界面——总不能把 749 行复制一遍再删删改改。

所以这一步做了件事：把 step12 的同一份 UI 原样提炼成一个包 `steps/cli_ui/`，留出干净的调用接口。界面本身（主题、欢迎框、历史、下拉框、`/model` 弹窗、状态栏、流式输出）和 step12 **一模一样**，一行行为都没改；只是从「一个写死的 App」变成了「一个可以继承的基类」。

**这章是 SDK 的使用文档，不再逐行讲原理。** 每个零件是怎么造出来的，回第 1-12 章看。

`cli_ui` 包内部结构（想深入的人对照源码和第 1-12 章读即可）：

- `cli_ui/theme.py` — Theme 定义（第 11 章的透明三要素：`ansi_default` + `ansi=True` + 两个 variables）。
- `cli_ui/widgets.py` — WelcomeBox / UserMessage / AssistantMessage / ToolCallMessage / SystemMessage / ChatScroll / StatusBar。除新增的 ToolCallMessage、SystemMessage 外，和 step12 对应代码一致。
- `cli_ui/inputs.py` — HistoryInput（第 08 章）+ CommandDropdown（第 09 章）。
- `cli_ui/modal.py` — ModelSelectModal（第 10 章的模型选择弹窗）。
- `cli_ui/app.py` — CliApp 基类和 AssistantHandle，把「提交 → 挂组件 → run_worker 流式输出」这条链路收进了框架。

## 快速开始

20 行跑出一个和 step12 同款的界面：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))  # cli_ui 在 steps/ 下

from cli_ui import CliApp

class Echo(CliApp):
    async def handle_input(self, text: str) -> None:
        assistant = await self.start_assistant()
        await assistant.write_answer(f"你说的是：**{text}**")
        await assistant.finish()

Echo(title="Echo", model="K3-256k", version="0.1.0").run()
```

跑起来就有：蓝色欢迎框、底部状态栏、`↑↓` 历史翻页、输入 `/` 弹下拉框、`/model` 弹模型选择窗、Esc 关弹窗、透明主题——全是内置的，你只写了三行业务代码。

## API 参考

### 构造参数

```python
CliApp(
    title="Kimi Code",        # 欢迎框里的 "Welcome to {title}!"
    model="K3-256k",          # 欢迎框和状态栏里的模型名
    version="0.34.0",         # 欢迎框里的版本号
    commands=[("clear", "Clear chat history")],  # 进下拉框的自定义命令
)
```

`commands` 是 `(命令名, 描述)` 的列表，输入 `/` 时下拉框按前缀过滤。`/model` 永远内置，不用（也不能只靠自己）加。

### `handle_input(text)` —— 必须实现

收到一条普通输入（非 `/` 开头）时被调用。框架自动做三件事：显示用户消息、把你的协程丢进 `run_worker` 后台跑（打字不卡）、App 退出时取消它（你在循环里 `await` 就行，框架内部的写入方法自己检查 `is_cancelled`，被取消后变成静默空操作）。

### `handle_command(command)` —— 可选覆写

收到 `/xxx` 时被调用（`command` 不带斜杠）。`/model` 内置弹窗，不会进这里。默认实现是显示一行灰色的 `Unknown command: /xxx`。

### 显示类方法（都是 async，在 `handle_input` 里直接 `await`）

- `assistant = await self.start_assistant()` —— 开一条新的 AI 消息，返回 **AssistantHandle**。
- `await assistant.write_thinking(s)` —— 往 thinking 行（灰点斜体）累加文本，可多次调用；首个字符到达前整行自动隐藏。
- `await assistant.write_answer(s)` —— 往 Markdown 回答累加文本，可多次调用；首个 chunk 到达前整行自动隐藏，流的首尾（`get_stream` / `stream.stop`）框架代管。
- `await assistant.finish()` —— 收尾，**必须调用**（worker 结束时框架会兜底，但请显式调）。
- `await self.show_tool_call(name, args, result=None)` —— 显示一条工具调用：一行 `⚡ Name(参数摘要)`，结果灰字缩进，超过 5 行截断成 `… (还有 N 行)`。
- `tool = await self.start_tool_call(name)` —— 流式版工具调用：返回 **ToolCallHandle**，`await tool.write_args(s)` 逐段累加参数（标题行实时刷新），`await tool.show_result(s)` 后补结果；`await tool.show_diff(s)` 显示一段 unified diff（红删绿增，编辑类工具用，时序上先于结果到达）。参数随模型流式输出时用这个；一次性给全用上面的 `show_tool_call()`。
- `self.set_working(state)` —— 输入框上方的运行状态行（spinner 动画）：`"idle"` / `"thinking"` / `"tool"` / `"working"`，传 `None` 收起。worker 结束时框架自动收起。
- `await self.show_system(text)` —— 显示一行灰色系统提示，适合错误和通知。
- `await self.show_user(text)` —— 手动补显示一条用户消息。提交时框架已自动显示，一般不需要调。

### `set_status(...)` —— 更新状态栏

```python
self.set_status(model="K3", context="context: 12% (30k/256k)")
```

四个参数 `model / directory / git_branch / context` 都是可选，传哪个更新哪个，同步方法（不需要 `await`）。

另外 `self.update_context(tokens)` 是专门的 context 快捷方式：传当前总 token 数，自动换算成 `context: 3% (8192/256k)` 刷到状态栏右侧（上限 256k），同步方法。

## step13_sdk.py 完整代码与讲解

```python
"""第 13 步：用 cli_ui SDK 做一个 agent（不再自己造界面）。…docstring 略…"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 让 cli_ui 可被 import

from cli_ui import CliApp


async def stream(write, text, delay=0.03, chunk=4):
    """把 text 按小块流式写给 write（write_thinking / write_answer）。"""
    for i in range(0, len(text), chunk):
        await write(text[i : i + chunk])
        await asyncio.sleep(delay)
```

`stream()` 是个小工具：把一大段文本按 4 字符一块、每块间隔 30ms 写给 `write_thinking` 或 `write_answer`，模拟真实 LLM 的流式输出。注意 `write` 直接传方法引用——SDK 的方法就是设计成可以这么玩的。

```python
class FakeAgent(CliApp):
    """一个假装会读文件、跑命令的 agent。"""

    async def handle_input(self, text: str) -> None:
        assistant = await self.start_assistant()
        await stream(assistant.write_thinking, f"用户问「{text}」，先看看项目里有什么……")

        await self.show_tool_call(
            "Read", "README.md",
            result="# 用 Textual 做 Claude Code 风格终端渲染\n\n本目录包含递增示例……",
        )
        await self.show_tool_call(
            "Bash", "ls steps/",
            result="\n".join(f"step{i:02d}_xxx.py" for i in range(1, 8)) + "\n...(略)",
        )

        await stream(assistant.write_answer, (
            f"你输入的是 **{text}**。\n\n"
            "这是一个 `cli_ui` SDK 的演示：\n"
            "- thinking、工具调用、Markdown 回答都是 `await` 一行搞定\n"
            "- 界面和第 12 步的成品完全相同（主题 / 历史 / 下拉框 / /model）"
        ))
        await assistant.finish()
        self.set_status(context="context: 1% (2.6k/256k)")
```

一条消息的典型流程全在这了：`start_assistant()` 开场 → `write_thinking` 流式思考 → `show_tool_call` 显示两次工具调用（Read 和 Bash，Bash 的结果超过 5 行会被自动截断）→ `write_answer` 流式输出 Markdown → `finish()` 收尾 → 顺手用 `set_status` 更新状态栏的上下文占用。

```python
    async def handle_command(self, command: str) -> None:
        await self.show_system(f"演示版没有实现 /{command}（/model 是内置的）")


if __name__ == "__main__":
    FakeAgent(
        title="cli_ui Demo",
        model="K3-256k",
        version="0.1.0",
        commands=[("clear", "Clear chat history"), ("about", "About this demo")],
    ).run()
```

`/clear` 和 `/about` 进了下拉框，选中后会调到上面的 `handle_command`；`/model` 由框架内置弹窗。对比一下：step12 把这些界面逻辑全写在 App 里用了 749 行，这里业务代码只有几十行。

## 运行与验证

```bash
python steps/step13_sdk.py
```

发一条消息，应该依次看到：thinking 灰字逐字出现 → 两行工具调用（`⚡ Read(README.md)` 和 `⚡ Bash(ls steps/)`，Bash 的结果截断成 5 行 + `… (还有 N 行)`）→ Markdown 回答流式蹦字 → 状态栏右侧变成 `context: 1% (2.6k/256k)`。再试试 `↑` 翻历史、输入 `/c` 看下拉框过滤出 `clear`、`/model` 弹窗、Esc 关闭。

无头验证（和第 5 章以来一样的 pilot 套路）也能跑通：启动自动聚焦、发消息后用户消息 / thinking / 工具调用行 / Markdown 回答 / 状态栏全部就位、`/model` 弹窗能开能关、未知命令显示灰色提示。

## 常见问题

**1. 为什么不能直接 `import step12_final` 来复用？**

step12 是个「写完的 App」而不是「能用的库」：`KimiStyleChatApp` 里模型名、命令列表、回答内容全是模块级常量或写死的字符串；`on_input_submitted` 收到消息后直接 `run_worker(self.stream_response(...))` 播一段固定文本——整条「输入 → 输出」的链路没有任何留给外部接的口子。你 import 进来也只能原样运行，想换掉假数据就得改它的源码。SDK 做的事就是在这条链路上开口子：`handle_input` / `handle_command` 留给子类，`show_*` 系列方法留给输出，其余原样保留。

**2. 想改主题 / 样式怎么办？**

两条路，按需选：

- **换主题**：自己定义一个 `Theme`（抄 `cli_ui/theme.py` 里的 `KIMI_THEME` 改颜色），传 `CliApp(theme=你的主题)`。注意透明三要素（`ansi_default` 背景、`ansi=True`、`variables` 补两个 ansi 变量）别丢，丢了透明终端下背景就不透了。
- **改样式**：继承 `CliApp` 后覆写类属性 `CSS`（框架自己的 CSS 在 `cli_ui/app.py` 里，先 `super().CSS` 拼上你自己的片段），或者给具体组件传 `classes` / 覆写组件的 `DEFAULT_CSS`。各组件自带 `DEFAULT_CSS`，直接 import 组件出来改子类也行。

**3. `handle_input` 里能不能用同步阻塞调用（比如 `requests.get`）？**

会卡住整个界面——它虽然跑在 worker 里，但 worker 也是同一个事件循环上的协程。同步阻塞调用请用 `asyncio.to_thread(...)` 或 Textual 的 `@work(thread=True)` 包一层。

**4. 忘了调 `assistant.finish()` 会怎样？**

worker 结束时框架会兜底帮你收尾（关掉还开着的 Markdown 流），所以不会报错；但显式调用是好习惯——`finish()` 之后这条消息的流式状态就彻底结束了，语义清楚。

**5. 想在 `handle_input` 之外的地方（比如按键回调）调用 `show_*` 系列？**

可以，它们是普通的 async 方法，在消息处理器里 `await` 一样安全；只是不在 worker 里时没有取消检查这一层保护（正常也用不到）。
