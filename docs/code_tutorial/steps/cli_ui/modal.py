"""模型选择弹窗（/model 内置命令使用）。从 step12_final.py 提炼，行为一致。"""

from typing import Any

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Horizontal, HorizontalGroup, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from .theme import ACCENT


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
        color: #c8cdd5;
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
        color: #c8cdd5;
    }
    #thinking-section Static {
        width: auto;
    }
    """

    BINDINGS = [
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
