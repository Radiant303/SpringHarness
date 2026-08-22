from spring_harness.console.cli_ui import AssistantHandle, CliApp, ToolCallHandle


class CliSink:
    def __init__(self, app: CliApp) -> None:
     self._app:CliApp = app
     self._assistant:AssistantHandle | None = None
     self._mode: str | None = None  # 当前气泡在装什么："thinking" / "answer" / "tool"
     self._app.set_working("idle")  # 消息已发出、内容未到达

    async def _ensure_assistant(self, mode: str) -> AssistantHandle:
        if self._assistant is None or self._mode != mode:
            await self._close_ensure_assistant()
            self._assistant = await self._app.start_assistant()
            self._mode = mode
        return self._assistant

    async def _close_ensure_assistant(self) -> None:
        if self._assistant is not None:
            await self._assistant.finish()
            self._assistant = None
            self._mode = None

    async def write_thinking(self, text: str):
        self._app.set_working("thinking")
        handle = await self._ensure_assistant("thinking")
        await  handle.write_thinking(text)

    async def write_answer(self, text: str):
        self._app.set_working("working")
        handle = await self._ensure_assistant("answer")
        await  handle.write_answer(text)

    async def start_tool_call(self, name: str) -> ToolCallHandle:
        self._app.set_working("tool")
        _handle = await self._close_ensure_assistant()
        return await self._app.start_tool_call(name)

    async def finish(self):
        self._app.set_working(None)
        await self._close_ensure_assistant()

    async def update_context(self, tokens: int) -> None:
        self._app.update_context(tokens)
