"""cli_ui：Claude Code / Kimi Code 风格终端聊天界面 SDK。

由教程第 12 步的成品（step12_final.py）提炼而成，用法::

    from cli_ui import CliApp

    class MyBot(CliApp):
        async def handle_input(self, text: str) -> None:
            assistant = await self.start_assistant()
            await assistant.write_answer(f"你说的是：{text}")
            await assistant.finish()

    MyBot(title="My Bot", model="K3-256k", version="0.1.0").run()
"""

from .app import AssistantHandle, CliApp, ToolCallHandle
from .inputs import CommandDropdown, HistoryInput
from .modal import ModelSelectModal
from .theme import ACCENT, KIMI_THEME
from .widgets import (
    AssistantMessage,
    ChatScroll,
    StatusBar,
    SystemMessage,
    ToolCallMessage,
    UserMessage,
    WelcomeBox,
)

__all__ = [
    "ACCENT",
    "KIMI_THEME",
    "CliApp",
    "AssistantHandle",
    "ToolCallHandle",
    "WelcomeBox",
    "UserMessage",
    "AssistantMessage",
    "ToolCallMessage",
    "SystemMessage",
    "ChatScroll",
    "StatusBar",
    "HistoryInput",
    "CommandDropdown",
    "ModelSelectModal",
]
