# 用 Textual 做 Claude Code 风格终端渲染（12 步细分教程）

本目录的 `steps/` 子目录包含 12 个**递增**的示例，每一步 = 上一步 + 一个新概念，
教你用 Textual 从零搭一个类似 Claude Code / Kimi Code CLI 的终端聊天界面。

每个文件都能独立运行，跑起来戳一戳就知道这步做了什么。

## 配套教程

`tutorial/` 目录有一套面向小白的手把手教程（从 [`tutorial/README.md`](tutorial/README.md) 开始），
每章对应一个 step，逐块讲解代码，跟着做即可手动实现 step12 的成品效果。

## 运行方式

确保已安装本仓库（在仓库根目录 `pip install -e .`，会连带装上依赖的 textual）：

```bash
cd code_tutorial
python steps/step01_basic.py      # 任意一步都可以直接跑
python steps/step12_final.py      # 成品
```

目录结构：`steps/` 是全部可运行代码（12 个 step + 它们依赖的 `steps/cjk_wrap.py`
和截图/验证脚本），`tutorial/` 是配套教程。

## 建议的学习方法

1. **先跑，再读。** 运行这一步的文件，戳一戳界面，再回头看代码。
2. **只看增量。** 每个文件的 docstring 开头都写着「学到什么」和「和第 N-1 步的区别」，
   用 `diff steps/step05_streaming.py steps/step06_thinking.py` 看差异，一次只消化一块。

## 12 步分别学什么

### steps/step01_basic.py：最小骨架
- `App` + `compose()`：界面的最小结构。
- `VerticalScroll` 聊天记录区 + `Input` 输入框（`dock: bottom` 钉在底部）。
- `on_input_submitted` 事件：回车后把消息挂进滚动区。
- 启动后自动聚焦输入框（`on_mount` 里 `input.focus()`）。

### steps/step02_scroll.py：自动滚动到底部
- `scroll.anchor()`：锚定后新消息会把视图自动顶到底部；用户手动上滚会解除锚定。
- `ChatScroll`：挡住 anchor 在「内容不足一屏」时写入的负 `scroll_y`，避免第一次发消息后日志整体下移。

### steps/step03_widgets.py：自定义消息组件
- 继承 `CJKStatic`（`steps/cjk_wrap.py` 里的中文友好换行版 `Static`，原理在 step07 统一讲）
  做 `UserMessage`（✨ 黄色前缀，用 `Text.assemble` 拼颜色）。
- `DEFAULT_CSS`：组件自带样式，跟着组件走。
- `scroll.mount()`：运行时动态往界面加组件。

### steps/step04_markdown.py：回答用 Markdown 渲染
- `Markdown` 组件：直接吃 Markdown 源文本（加粗、列表、代码块）。
- `AssistantMessage` 升级成 `Vertical` 容器，`HorizontalGroup` 把 ● 圆点和回答横排。
- Markdown 默认 `padding: 0 2`，要 `padding: 0` 才能和圆点对齐。

### steps/step05_streaming.py：流式输出（一个字一个字蹦）
- `Markdown.get_stream(md)` 拿到流写入器，反复 `await stream.write(片段)`。
- `run_worker()` 把流式循环放后台跑 —— 不然流没结束，按键全卡住。
- `.stream-pending { display: none; }`：回答首个 chunk 到达前隐藏整行，避免空的 `●` 提前出现。
- `finally: await stream.stop()`：流一定要收尾。

### steps/step06_thinking.py：思考过程行
- 一个组件里两行结构：thinking-row（灰点 + 灰斜体）+ answer-row（白点 + Markdown）。
- 同一个流式技巧用两次：先逐字写思考（`Static.update`），再流式写回答。
- 两行分别等自己的首个字符到达才移除 `stream-pending`；thinking 一直展开，不折叠。

### steps/step07_styling.py：CSS 美化（开始像真的了）
- `WelcomeBox`：`border: round #4a9eff` 圆角蓝框 + 色块 logo + Directory/Session/Model/Version。
- 输入框变身：外层 `Horizontal` 画边框，里面 `> ` 提示符 + `border: none` 的 Input。
- `margin` 调消息间距；`MarkdownParagraph:last-child { margin-bottom: 0 }` 去掉尾巴空行。
- `CJKMarkdown` 修复 Markdown 回答的中文提前换行；`CJKStatic` 用同一套规则修复用户消息和 thinking。

### steps/step08_history.py：命令历史（↑↓ 翻）
- 继承 `Input` 做 `HistoryInput`：`_history` 列表 + `_history_pos` 游标 + `_draft` 草稿。
- `on_key` 里拦截 ↑↓，`event.stop()` 防止按键继续传播。
- 翻历史前先存草稿，翻到底（↓ 过头）恢复草稿。

### steps/step09_dropdown.py：斜杠命令下拉框
- 输入 `/` 弹出 `CommandDropdown`，`@on(Input.Changed)` 实时过滤。
- 键盘事件「双模式」：下拉框可见时 ↑↓/Enter/Esc 归下拉框，否则归历史翻页。
- **防闪烁**：切换选中只 `set_class` + 改箭头文字，不重建组件；
  列表内容真变了才 `remove_children()` + `mount_all()` 一次重建。

### steps/step10_modal.py：模态弹窗
- `ModalScreen`：盖在主界面上的一层屏幕；`push_screen()` 推上去，`dismiss()` 拿掉。
- `BINDINGS = [("escape", "cancel", ...)]`：Esc 关弹窗。
- `/model` 命令真正弹出模型选择窗口（标题/帮助/警告/标签页/列表全是 Static 组合）。

### steps/step11_theme.py：主题与全透明背景
- `Theme` 对象一次定义全套颜色；`register_theme()` + `self.theme = "kimi"` 启用。
- **透明的关键**（App 层面就够，不用动 Textual 源码）：
  1. `background/surface/panel` 设为 `ansi_default` —— 输出 SGR `49`（终端默认背景），
     终端自己的背景（含半透明）就能透出来。
  2. `Theme(ansi=True)` —— 禁用 ANSI→RGB 过滤器，否则 `ansi_default` 会被解析成
     `#0c0c0c` 之类的固定色，透明失效。内置 `ansi-dark` / `ansi-light` 主题就是这个原理。
  3. `ansi=True` 的主题要在 `variables` 里补 `ansi-background` / `ansi-foreground`
     （按钮、Toast、内联边框会引用）。
- 其余组件保持 `background: transparent`，背景沿组件链一路混合成 `ansi_default`。
- 验证：`python steps/ansi_dump.py` 应看到 `49` 出现、没有 `48;2;0;0;0`（不透明黑）。
  注意 `steps/ansi_dump.py` 实际渲染的是 step12 的 App（导入了 `step12_final`）。

### steps/step12_final.py：成品
- 前 11 步的主体 + `StatusBar` 底部状态栏（模型/目录/git 分支/上下文用量）。
  （布局从 `dock: bottom` 改回纵向流以容纳状态栏；`/yolo` 等演示命令的
  「已选中」分支被去掉，除 `/model` 外的未知命令会提示 Unknown command。）
- 开屏提示行 / 警告行（静态展示，模仿真实 CLI）。
- 流式输出带 `worker.is_cancelled` 检查，退出时后台流干净停掉。

### steps/step13_sdk.py：SDK 封装（开箱即用）
- 前 12 步是「教你怎么造」，这一步是把 step12 的界面提炼成 `steps/cli_ui/` 包，
  用的人不用懂 Textual：继承 `CliApp`，实现 `handle_input()`，
  调 `start_assistant()` / `start_tool_call()` / `show_tool_call()` / `show_system()` / `set_status()` / `set_working()` 即可。
- 包内模块：`theme.py`（透明主题）、`widgets.py`（消息/状态栏组件，含新增的
  `ToolCallMessage`）、`inputs.py`（历史输入 + 斜杠下拉框）、`modal.py`（模型选择弹窗）、
  `app.py`（CliApp 基类）。详细用法见 `tutorial/13_SDK封装.md`。

## 踩过的坑（前面步骤里都会遇到，集中备忘）

- `Horizontal` / `Vertical` 容器默认 `height: 1fr`，放在 `height: auto` 的父容器里
  会把父容器撑满整屏。需要自动高度的行请用 `HorizontalGroup`。
- `Static` 默认 `width: 1fr`，在水平排列里要加 `width: auto`，否则会挤掉后面的内容。
- `background: transparent` 只表示「和下层混合」；如果整条链路都 transparent，
  最终透明黑会退化成不透明黑，在透明终端里表现为文字后面拖深色块。
  正确做法见 step11（最底层用 `ansi_default`）。
- 截图时如果环境变量 `NO_COLOR=1`，Textual 会进入灰度模式。
  生成彩色截图用 `env -u NO_COLOR python xxx.py`
  （PowerShell：先 `$env:NO_COLOR=""` 再运行）。
- App 要在 `on_mount` 里显式 `input.focus()`（step01 起每个 App 都有），
  否则按键焦点会被可滚动的聊天区抢走，打字没反应。
- **第一次发消息后，日志整体下移、顶部空一片**：`anchor()` 会让滚动区持续吸底；
  但 Textual 合成器在内容不足一屏时，用 `set_reactive()` 直接写入
  `内容高度 - 可视高度`，结果是负的 `scroll_y`，还绕过了正常的 0 下限校验。
  解法（不用改 Textual 源码）：step02 起使用 `ChatScroll`，只拦截
  `Widget.scroll_y` / `Widget.scroll_target_y` 的负值并钳制到 0；内容真正超屏时
  anchor 仍然正常吸底，用户手动上滚也仍会解除锚定。
- **中文长段落「提前换行、右侧一大片空白」**：Textual 的文本换行走 Rich 的
  `divide_line()`，它按空格分词 —— 一段没有空格的中文会被当成一个超长的「词」，
  只要它比整行窄，就会被整体挪到下一行，当前行写了一半就换行了。
  解法（不用改 Textual 源码）：`steps/cjk_wrap.py` 里的 `cjk_divide_line()` 自己算断行
  （优先空格断、CJK 宽字符之间随时可断、超长单词才硬折），再用一个 `Visual`
  包装层把预断行后的内容交回原生渲染流程；`CJKMarkdown` 用于 Markdown 回答，
  `CJKStatic` 用于用户消息和 thinking。启用时间线：`CJKStatic` 从 step03 起
  用于用户消息、step06 起用于 thinking；step07 起 Markdown 回答也换成
  `CJKMarkdown`，三类消息至此全部使用 CJK 友好换行。

## 截图与验证

生成成品截图（SVG，再用任意工具转 PNG 查看）：

```bash
env -u NO_COLOR python steps/screenshot_final.py   # 输出 final_chat/dropdown/model.svg
```

`steps/screenshot_final.py` 只处理导出的 SVG：

- 使用 Windows 常见的 `Noto Sans SC` / `Segoe UI Symbol` 字体，避免中文和 `✨` 变成方框；
- 把 Rich 按字符数计算的 SVG `textLength` 修正为终端 cell 宽度，避免中文和英文之间出现假空白；
- 不修改 Textual 源码，也不改变应用在真实终端中的换行和布局。

验证透明背景是否真的生效：

```bash
env -u NO_COLOR python steps/ansi_dump.py
```

## 下一步可以做的扩展

- 把 `run_worker(self.stream_response(...))` 换成真实的 LLM API 调用。
- 给 `AssistantMessage` 里的 `Markdown` 加复制按钮（自定义 `MarkdownBlock`）。
- 支持多轮对话上下文、清空对话、保存聊天记录到文件。
- 给输入框加 Tab 自动补全（命令或文件路径）。
