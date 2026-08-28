"""弹窗：模型选择（/model 内置命令）、工具批准（deferred 调用挂起时）。"""

import json
from typing import Any, ClassVar

from pydantic_ai import ToolCallPart
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, HorizontalGroup, Vertical, VerticalScroll
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
        scrollbar-color-hover: #7a8391;
        scrollbar-color-active: #7a8391;
        scrollbar-background: #0b0d10;  /* 跟随面板底色 */
    }
    #approval-help {
        color: #7a8391;
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
                Text.assemble(("⚡ ", ACCENT), (self._call.tool_name, "bold"), (f"({args})", "#9aa3b0")),
                id="approval-call",
            )
            if self._diff:
                with VerticalScroll(id="approval-preview"):
                    yield Static(self._render_preview())
            yield Static(
                Text.assemble(
                    ("[y]", "bold #e5c07b"), (" Approve   ", "#9aa3b0"),
                    ("[n]", "bold #e5c07b"), (" Reject   ", "#9aa3b0"),
                    ("[Esc]", "bold #e5c07b"), (" Reject", "#9aa3b0"),
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


class ModelSelectModal(ModalScreen[None]):
    """模型选择弹窗（简化版）。"""

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
        color: #7a8391;
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
        color: #7a8391;
    }
    .provider-tab.-active {
        background: #4a9eff;
        color: #ffffff;
        text-style: bold;
    }
    #model-list {
        height: auto;
        max-height: 10;
    }
    #model-list .model-name {
        width: 24;
        color: ansi_default;
    }
    #model-list .model-current {
        color: #4a9eff;
    }
    #model-list .model-provider {
        color: #7a8391;
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
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        models: list[tuple[str, str]] | None = None,
        current_model: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._models = models if models is not None else [
            ("K2.7 Coding Highspeed", "Kimi Code"),
            ("K3", "Kimi Code"),
            ("K3-256k", "Kimi Code"),
        ]
        self._current_model = current_model

    def compose(self) -> ComposeResult:
        with Vertical(id="model-dialog"):
            yield Static("Select a model  (type to search)", id="model-title")
            yield Static("Tab toggle provider · ↑↓ navigate · Enter select · Alt+S session-only · Esc cancel", id="model-help")
            yield Static("Note: Switching models invalidates the existing prompt cache. Use /new to avoid extra token costs.", id="model-warning")

            with Horizontal(id="provider-tabs"):
                yield Static(" All ", classes="provider-tab -active")
                yield Static(" ruoli ", classes="provider-tab")
                yield Static(" deepseek ", classes="provider-tab")

            with Vertical(id="model-list"):
                for name, provider in self._models:
                    is_current = name == self._current_model
                    name_text = f"> {name}" if is_current else f"  {name}"
                    name_classes = "model-name model-current" if is_current else "model-name"
                    provider_text = f"{provider} ← current" if is_current else provider
                    yield HorizontalGroup(
                        Static(name_text, classes=name_classes),
                        Static(provider_text, classes="model-provider"),
                    )

            with Horizontal(id="thinking-section"):
                yield Static("Thinking  (←→ to switch)   ")
                yield Static(" Low   ")
                yield Static(Text("[ High ]", style=f"bold {ACCENT}"))
                yield Static("   Max")

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
        color: #7a8391;
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
        scrollbar-color-hover: #7a8391;
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
