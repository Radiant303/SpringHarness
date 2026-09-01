"""弹窗：模型选择（/model 内置命令）、工具批准（deferred 调用挂起时）。"""

import json
from typing import Any, ClassVar

from pydantic_ai import ToolCallPart
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.highlight import highlight
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from .cjk_wrap import DiffHighlightTheme
from .theme import ACCENT


def _args_preview(args: object) -> str:
    """参数摘要：dict 用 JSON 序列化（和聊天区工具头的双引号格式一致）。"""
    if args is None:
        return ""
    if isinstance(args, dict):
        return json.dumps(args, ensure_ascii=False)
    return str(args)


class ApprovalModal(ModalScreen[bool]):
    """单条工具调用的批准弹窗：y 批准这一条、n/Esc 拒绝这一条。

    多条挂起调用由调用方逐个弹（Claude Code 风格：每个工具各问一次）。
    编辑类工具可传 diff 预览（调用方用 renderer.make_diff 生成），
    审批决策最需要看的就是改动内容，而不是被截断的 JSON 参数。
    """

    CSS = """
    ApprovalModal {
        align: center middle;
        background: black 60%;  /* 压暗背后的聊天内容，弹窗才是焦点 */
    }
    #approval-dialog {
        width: 90%;          /* 自适应终端宽度，长 diff 行不再被裁 */
        max-width: 140;
        height: auto;
        /* 近黑底色：与压暗背景融为一体，圆角边框角落不露出方块感（同 SessionSelectModal） */
        background: #0b0d10;
        border: round #e5c07b;
        padding: 1 2;
    }
    #approval-title {
        color: #e5c07b;
        text-style: bold;
        margin-bottom: 1;
    }
    #approval-call {
        height: auto;
        margin-bottom: 1;
    }
    #approval-preview {
        height: auto;
        max-height: 16;      /* 超高出滚动，不再截断内容 */
        margin-bottom: 1;
        padding-left: 2;
        border-left: solid #3a3f4a;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 1;
        /* 默认滚动条是刺眼的 ANSI 蓝，换成和引导线一致的灰 */
        scrollbar-color: #3a3f4a;
        scrollbar-color-hover: ansi_bright_black;
        scrollbar-color-active: ansi_bright_black;
        scrollbar-background: #0b0d10;  /* 跟随面板底色 */
    }
    #approval-help {
        color: ansi_bright_black;
    }
    """

    BINDINGS: ClassVar[list] = [
        ("y", "approve", "Approve"),
        ("Y", "approve", "Approve"),  # Textual 键区分大小写，Shift/CapsLock 下的 Y 也要生效
        ("n", "reject", "Reject"),
        ("N", "reject", "Reject"),
        ("escape", "reject", "Reject"),
    ]

    MAX_ARGS_LEN = 60

    def __init__(self, call: ToolCallPart, diff: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._call = call
        self._diff = diff

    def on_mount(self) -> None:
        # 聚焦滚动区：↑↓/PgUp/PgDn 直接滚动 diff（y/n 是 screen 级绑定，不受影响）
        if self._diff:
            self.query_one("#approval-preview", VerticalScroll).focus()

    def compose(self) -> ComposeResult:
        args = _args_preview(self._call.args)
        if len(args) > self.MAX_ARGS_LEN:
            args = args[: self.MAX_ARGS_LEN - 1] + "…"
        with Vertical(id="approval-dialog"):
            yield Static("Approve this tool call?", id="approval-title")
            yield Static(
                Text.assemble(("⚡ ", ACCENT), (self._call.tool_name, "bold"), (f"({args})", "default")),
                id="approval-call",
            )
            if self._diff:
                with VerticalScroll(id="approval-preview"):
                    yield Static(self._render_preview())
            yield Static(
                Text.assemble(
                    ("[y]", "bold #e5c07b"), (" Approve   ", "default"),
                    ("[n]", "bold #e5c07b"), (" Reject   ", "default"),
                    ("[Esc]", "bold #e5c07b"), (" Reject", "default"),
                ),
                id="approval-help",
            )

    def _render_preview(self) -> Content:
        """diff 完整预览（红绿高亮）；内容超出预览区高度时滚动查看，不截断。"""
        return highlight(self._diff or "", language="diff", theme=DiffHighlightTheme)

    def action_approve(self) -> None:
        self.dismiss(True)

    def action_reject(self) -> None:
        self.dismiss(False)


class ModelSelectModal(ModalScreen[tuple[str, bool] | None]):
    """模型选择弹窗：Tab 循环切换 provider 过滤，↑↓ 选择，Esc 取消。

    Enter 确认 = 切换并写回默认配置；Alt+S = 仅本次会话切换（不写盘）。
    dismiss 返回 (模型id, 是否写回默认配置)，None 表示取消。
    models 每项为 (模型id, 显示名, provider)；current_model 传当前模型 id：
    "> " 前缀 + 主题色标记，并作为初始高亮项。
    Thinking 行为静态展示，不可交互。
    """

    CSS = """
    ModelSelectModal {
        align: center middle;
    }
    #model-dialog {
        width: 70;
        height: auto;
        background: transparent;
        border: round #4a9eff;
        padding: 1 2;
    }
    #model-title {
        color: #4a9eff;
        text-style: bold;
        margin-bottom: 1;
    }
    #model-help {
        color: ansi_bright_black;
        margin-bottom: 1;
    }
    #model-warning {
        color: #e5c07b;
        margin-bottom: 1;
    }
    #provider-tabs {
        height: auto;
        margin-bottom: 1;
    }
    .provider-tab {
        width: auto;
        padding: 0 2;
        background: transparent;
        color: ansi_bright_black;
    }
    .provider-tab.-active {
        background: #4a9eff;
        color: #ffffff;
        text-style: bold;
    }
    #model-list {
        height: auto;
        max-height: 10;  /* 超高滚动 */
        background: transparent;
        border: none;    /* OptionList 自带的框是第二层嵌套边框，干掉 */
        padding: 0;
        scrollbar-size-vertical: 1;
        scrollbar-color: #3a3f4a;
        scrollbar-color-hover: ansi_bright_black;
        scrollbar-background: transparent;
    }
    #model-list .option-list--option-highlighted {
        /* 默认高亮是刺眼的亮紫底，换成克制的深灰 */
        background: #2a2f3a;
        color: ansi_default;
    }
    #model-list .option-list--option-hover {
        /* 鼠标悬停默认也是紫底，一并收编 */
        background: #23272f;
    }
    #thinking-section {
        height: auto;
        margin-top: 1;
        color: ansi_default;
    }
    #thinking-section Static {
        width: auto;
    }
    """

    BINDINGS: ClassVar[list] = [
        # priority：压过 App 层的 Tab=切换焦点 默认行为
        Binding("tab", "next_provider", "Next provider", priority=True),
        ("alt+s", "session_only", "Session only"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        models: list[tuple[str, str, str]],
        current_model: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._models = models
        self._current_model = current_model
        # provider 标签页从模型列表派生，按出现顺序去重
        self._providers: list[str] = []
        for _, _, provider in models:
            if provider not in self._providers:
                self._providers.append(provider)
        self._active_provider: str | None = None  # None = All（不过滤）

    def _visible_models(self) -> list[tuple[str, str, str]]:
        """当前标签页下可见的模型；All 时不过滤。"""
        if self._active_provider is None:
            return self._models
        return [m for m in self._models if m[2] == self._active_provider]

    def _options(self) -> list[Option]:
        # 列表行复刻旧样式：名称列宽 24，当前项 "> " 前缀 + 主题色
        options = []
        for model_id, display_name, provider in self._visible_models():
            if model_id == self._current_model:
                options.append(Option(Text.assemble(
                    (f"> {display_name:<24}", f"bold {ACCENT}"),
                    (provider, "bright_black"),
                )))
            else:
                options.append(Option(Text.assemble(
                    f"  {display_name:<24}",
                    (provider, "bright_black"),
                )))
        return options

    def compose(self) -> ComposeResult:
        with Vertical(id="model-dialog"):
            yield Static("Select a model  (type to search)", id="model-title")
            yield Static("Tab toggle provider · ↑↓ navigate · Enter select · Alt+S session-only · Esc cancel", id="model-help")
            yield Static("Note: Switching models invalidates the existing prompt cache. Use /new to avoid extra token costs.", id="model-warning")

            with Horizontal(id="provider-tabs"):
                yield Static(" All ", id="tab-all", classes="provider-tab -active")
                for provider in self._providers:
                    yield Static(f" {provider} ", id=f"tab-{provider}", classes="provider-tab")

            yield OptionList(*self._options(), id="model-list")

            with Horizontal(id="thinking-section"):
                yield Static("Thinking  (←→ to switch)   ")
                yield Static(" Low   ")
                yield Static(Text("[ High ]", style=f"bold {ACCENT}"))
                yield Static("   Max")

    def on_mount(self) -> None:
        option_list = self.query_one(OptionList)
        option_list.focus()
        for i, (model_id, _, _) in enumerate(self._visible_models()):
            if model_id == self._current_model:
                option_list.highlighted = i
                break

    def action_next_provider(self) -> None:
        """Tab：在 All → 各 provider 之间循环，重建过滤后的列表。"""
        choices: list[str | None] = [None, *self._providers]
        idx = choices.index(self._active_provider)
        self._active_provider = choices[(idx + 1) % len(choices)]

        self.query_one("#tab-all", Static).set_class(self._active_provider is None, "-active")
        for provider in self._providers:
            self.query_one(f"#tab-{provider}", Static).set_class(
                self._active_provider == provider, "-active"
            )

        option_list = self.query_one(OptionList)
        option_list.clear_options()
        options = self._options()
        if options:
            option_list.add_options(options)
            option_list.highlighted = 0

    @on(OptionList.OptionSelected)
    def _select(self, event: OptionList.OptionSelected) -> None:
        # option_index 是过滤后列表里的下标，必须经 _visible_models 映射回模型 id
        model_id = self._visible_models()[event.option_index][0]
        self.dismiss((model_id, True))

    def action_session_only(self) -> None:
        """Alt+S：切换当前高亮的模型，但不写回默认配置（仅本次会话生效）。"""
        highlighted = self.query_one(OptionList).highlighted
        if highlighted is None:
            return
        model_id = self._visible_models()[highlighted][0]
        self.dismiss((model_id, False))

    def action_cancel(self) -> None:
        self.dismiss(None)


class SessionSelectModal(ModalScreen[int | None]):
    """会话选择弹窗：↑↓ 选择，Enter 确认，Esc 取消。

    dismiss 返回列表下标（调用方按新→旧排序传入），None 表示取消。
    current 传当前会话在列表中的下标：高亮色 + ● 标记，并作为初始高亮项。
    """

    CSS = """
    SessionSelectModal {
        align: center middle;
        background: black 60%;  /* 压暗背后的聊天内容，弹窗才是焦点 */
    }
    #session-dialog {
        width: 72;
        height: auto;
        /* 近黑底色：与压暗后的背景融为一体，圆角边框的角落格子不再露出方块感。
           面板感交给蓝色描边，不靠底色。 */
        background: #0b0d10;
        border: round #4a9eff;
        padding: 1 2;
    }
    #session-title {
        color: #4a9eff;
        text-style: bold;
    }
    #session-help {
        color: ansi_bright_black;
        margin-bottom: 1;
    }
    #session-list {
        height: auto;
        max-height: 12;  /* 超高滚动 */
        background: transparent;
        border: none;    /* OptionList 自带的框是第二层嵌套边框，干掉 */
        padding: 0;
        scrollbar-size-vertical: 1;
        scrollbar-color: #3a3f4a;
        scrollbar-color-hover: ansi_bright_black;
        scrollbar-background: #0b0d10;  /* 跟随面板底色 */
    }
    #session-list .option-list--option-highlighted {
        /* 默认高亮是刺眼的亮紫底，换成克制的深灰 */
        background: #2a2f3a;
        color: ansi_default;
    }
    #session-list .option-list--option-hover {
        /* 鼠标悬停默认也是紫底，一并收编 */
        background: #23272f;
    }
    """

    BINDINGS: ClassVar[list] = [("escape", "cancel", "Cancel")]

    def __init__(self, items: list[str], current: int | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._items = items
        self._current = current

    def compose(self) -> ComposeResult:
        options = []
        for i, label in enumerate(self._items):
            if i == self._current:
                # 当前会话：主题色加粗 + 圆点标记
                options.append(Option(Text.assemble(("● ", ACCENT), (label, f"bold {ACCENT}"))))
            else:
                options.append(Option(f"  {label}"))
        with Vertical(id="session-dialog"):
            yield Static("Resume session", id="session-title")
            yield Static("↑↓ navigate · Enter select · Esc cancel", id="session-help")
            yield OptionList(*options, id="session-list")

    def on_mount(self) -> None:
        option_list = self.query_one(OptionList)
        option_list.focus()
        if self._current is not None and self._items:
            option_list.highlighted = self._current

    @on(OptionList.OptionSelected)
    def _select(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_index)

    def action_cancel(self) -> None:
        self.dismiss(None)
