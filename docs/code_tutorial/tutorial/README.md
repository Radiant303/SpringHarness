# Textual 终端聊天界面教程（Claude Code / Kimi Code 风格）

面向 Python 初学者的手把手教程：跟着 12 章顺序做下来，你将从零用 Textual
手动实现一个带流式输出、思考过程、命令历史、斜杠命令下拉框、模态弹窗、
主题透明背景和底部状态栏的终端聊天界面（即 `../steps/step12_final.py` 的效果）。

每一章对应仓库 `steps/` 目录下的一个可运行示例 `stepNN_*.py`，结构统一为：
**本步目标 → 新概念 → 动手实现（分块讲解）→ 完整代码 → 运行与验证 → 常见问题**。

## 目录

| 章 | 内容 | 对应代码 |
|---|---|---|
| [01 最小骨架](01_最小骨架.md) | 环境准备、App / compose() / Input / mount | `steps/step01_basic.py` |
| [02 自动滚动](02_自动滚动.md) | anchor() 吸底、ChatScroll 钳制负 scroll_y | `steps/step02_scroll.py` |
| [03 自定义消息组件](03_自定义消息组件.md) | 继承 Static、DEFAULT_CSS、Text.assemble | `steps/step03_widgets.py` |
| [04 Markdown 渲染](04_Markdown渲染.md) | Markdown 组件、HorizontalGroup 横排 | `steps/step04_markdown.py` |
| [05 流式输出](05_流式输出.md) | Markdown.get_stream、run_worker、等待态 | `steps/step05_streaming.py` |
| [06 思考过程](06_思考过程.md) | thinking + answer 两行结构、Static.update | `steps/step06_thinking.py` |
| [07 CSS 美化](07_CSS美化.md) | 欢迎框、输入框造型、CJK 中文换行修复 | `steps/step07_styling.py` |
| [08 命令历史](08_命令历史.md) | HistoryInput、↑↓ 翻历史、草稿保存 | `steps/step08_history.py` |
| [09 斜杠命令下拉框](09_斜杠命令下拉框.md) | 实时过滤、键盘双模式、防闪烁 | `steps/step09_dropdown.py` |
| [10 模态弹窗](10_模态弹窗.md) | ModalScreen、push_screen / dismiss、BINDINGS | `steps/step10_modal.py` |
| [11 主题与透明背景](11_主题与透明背景.md) | Theme、ansi_default、终端透明透出 | `steps/step11_theme.py` |
| [12 成品与状态栏](12_成品与状态栏.md) | StatusBar、流取消、全系列回顾与扩展 | `steps/step12_final.py` |
| [13 SDK 封装](13_SDK封装.md) | 把成品提炼成 `cli_ui` 包，继承 CliApp 开箱即用 | `steps/step13_sdk.py` |

第 13 章和前 12 章定位不同：不是教你造轮子，而是把第 12 章的成品封装成
`steps/cli_ui/` SDK——显示用户消息、思考过程、工具调用、流式回答、状态栏都是
现成方法，直接拿来搭自己的 CLI agent。

## 学习建议

1. **按顺序做**，每章都建立在前一章的代码之上。
2. **先跑再读**：每章开头先运行对应的 `steps/stepNN_*.py` 戳一戳界面，再回头跟着写。
3. 环境准备见 [第 01 章](01_最小骨架.md) 开头；根目录的 `../README.md` 有速查式的概要。
