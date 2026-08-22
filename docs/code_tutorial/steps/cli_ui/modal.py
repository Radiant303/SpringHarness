"""弹窗：模型选择（/model 内置命令）、工具批准（deferred 调用挂起时）。"""

from typing import Any, ClassVar

from pydantic_ai import ToolCallPart
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, HorizontalGroup, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from .theme import ACCENT


class ApprovalModal(ModalScreen[bool]):
    """单条工具调用的批准弹窗：y 批准这一条、n/Esc 拒绝这一条。

    多条挂起调用由调用方逐个弹（Claude Code 风格：每个工具各问一次）。
    """

    CSS = """
    ApprovalModal {
        align: center middle;
    }
    #approval-dialog {
        width: 72;
        height: auto;
        background: transparent;
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
    #approval-help {
        color: #7a8391;
    }
    """

    BINDINGS: ClassVar[list] = [
        ("y", "approve", "Approve"),
        ("n", "reject", "Reject"),
        ("escape", "reject", "Reject"),
    ]

    MAX_ARGS_LEN = 60

    def __init__(self, call: ToolCallPart, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._call = call

    def compose(self) -> ComposeResult:
        args = str(self._call.args or "")
        if len(args) > self.MAX_ARGS_LEN:
            args = args[: self.MAX_ARGS_LEN - 1] + "…"
        with Vertical(id="approval-dialog"):
            yield Static("Approve this tool call?", id="approval-title")
            yield Static(
                Text.assemble(("⚡ ", ACCENT), (self._call.tool_name, "bold"), (f"({args})", "#9aa3b0")),
                id="approval-call",
            )
            yield Static("y approve · n reject · Esc reject", id="approval-help")

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
