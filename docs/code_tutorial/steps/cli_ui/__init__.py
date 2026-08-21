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

import sys
from pathlib import Path

# cjk_wrap.py 在本包的上一级目录（steps/），不在包内，这里把它所在的目录
# 加进 sys.path，保证 `from cli_ui import CliApp` 在任何工作目录下都能用。
_STEPS_DIR = str(Path(__file__).resolve().parent.parent)
if _STEPS_DIR not in sys.path:
    sys.path.insert(0, _STEPS_DIR)

from .app import AssistantHandle, CliApp
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
