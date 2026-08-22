"""CliSink：RenderSink 协议的 cli_ui 实现（Adapter）。

把 sink 调用翻译成 CliApp / AssistantHandle / ToolCallHandle 的操作。
AI 消息句柄惰性创建（首个 thinking/answer 到达时才 start_assistant），
所以一场没有正文、只有工具调用的运行不会留下空气泡。
"""


from typing import Any

from spring_harness.console.cli_ui import AssistantHandle, CliApp, ToolCallHandle


class CliSink:
    def __init__(self, app: CliApp) -> None:
     self._app:CliApp = app
     self._assistant:AssistantHandle | None = None

    async def _ensure_assistant(self) -> AssistantHandle:
        if self._assistant is None:
            self._assistant = await self._app.start_assistant()
        return self._assistant

    async def write_thinking(self, text: str):
        handle = await self._ensure_assistant()
        await  handle.write_thinking(text)

    async def write_answer(self, text: str):
        handle = await self._ensure_assistant()
        await  handle.write_answer(text)

    async def start_tool_call(self, name: str) -> ToolCallHandle:
        return await self._app.start_tool_call(name)

    async def finish(self):
        if self._assistant is not None:
            await self._assistant.finish()
