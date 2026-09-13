import asyncio
import subprocess
import sys
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
from pydantic_ai import ModelMessage
from pydantic_ai.messages import ModelMessagesTypeAdapter

from spring_harness.core.history import HistoryDirection, HistoryPage
from spring_harness.core.log import logger
from spring_harness.core.rpc.connection import (
    METHOD_NOT_FOUND,
    JsonRpcConnection,
    JsonRpcError,
)
from spring_harness.core.rpc.schema import (
    ApprovalRequestParams,
    ApprovalResult,
    AttachParams,
    HistoryQueryParams,
    HistoryResult,
    QuestionRequestParams,
    QuestionResult,
    SessionEventParams,
    SessionListResult,
    SessionParams,
    SessionResult,
    SessionSummary,
    SetModelParams,
    TurnStartParams,
    WorkspaceParams,
)
from spring_harness.core.stream.events import ServerEvent, TurnFinished

_EVENT = TypeAdapter(ServerEvent)

# 传输三件套：读线、写线、关闭。默认实现是 stdio 子进程，测试注入内存管道
Transport = tuple[
    Callable[[], Awaitable[str | None]],
    Callable[[str], Awaitable[None]],
    Callable[[], None],
]


class AppClient:
    def __init__(
        self,
        workspace: str | Path,
        *,
        on_approval: Callable[[ApprovalRequestParams], Awaitable[bool]],
        on_question: Callable[[QuestionRequestParams], Awaitable[str | None]],
        spawn: Callable[[], Transport] | None = None,  # 测试注入
    ) -> None:
        self._workspace = Path(workspace).resolve()
        self._on_approval = on_approval
        self._on_question = on_question
        self._spawn = spawn or self._spawn_stdio
        self.session_id: str | None = None
        self._events: asyncio.Queue[ServerEvent] = asyncio.Queue()
        self._turn_active = False
        self._connection: JsonRpcConnection | None = None
        self._connection_task: asyncio.Task[None] | None = None
        self._close_transport: Callable[[], None] = lambda: None

    # ---- 生命周期 ----

    async def connect(self) -> None:
        read_line, write_line, self._close_transport = self._spawn()
        self._connection = JsonRpcConnection(read_line, write_line)
        self._connection_task = asyncio.create_task(self._run_connection())
        await self._connection.send_request("initialize", {})

    async def close(self) -> None:
        self._close_transport()
        if self._connection_task is not None:
            self._connection_task.cancel()
            try:
                await self._connection_task
            except asyncio.CancelledError:
                pass

    async def _run_connection(self) -> None:
        assert self._connection is not None
        try:
            await self._connection.run(self._on_request, self._on_notification)
        finally:
            # 连接中断时轮次永远没有 TurnFinished，补一个让泵能收尾
            if self._turn_active:
                self._turn_active = False
                await self._events.put(TurnFinished(error="与 app server 的连接已断开"))

    # ---- 会话操作（与服务端方法一一对应）----

    async def new_session(self, model: str | None = None) -> str:
        result = await self._request("session/new", WorkspaceParams(workspace=str(self._workspace), model=model))
        return self._bind_session(result)

    async def resume_last(self, model: str | None = None) -> str | None:
        result = await self._request("session/resume_last", WorkspaceParams(workspace=str(self._workspace), model=model))
        session_id = SessionResult.model_validate(result).session_id
        if session_id is not None:
            self.session_id = session_id
        return session_id

    async def list_sessions(self) -> list[SessionSummary]:
        result = await self._request("session/list", WorkspaceParams(workspace=str(self._workspace)))
        return SessionListResult.model_validate(result).sessions

    async def attach(self, session_id: str, model: str | None = None) -> str:
        result = await self._request(
            "session/attach",
            AttachParams(workspace=str(self._workspace), session_id=session_id, model=model),
        )
        return self._bind_session(result)

    async def history(
        self,
        cursor: str | None = None,
        limit: int | None = None,
        direction: HistoryDirection = "forward",
    ) -> list[list[ModelMessage]]:
        return (await self.query_history(cursor, limit, direction)).segments

    async def query_history(
        self,
        cursor: str | None = None,
        limit: int | None = None,
        direction: HistoryDirection = "forward",
    ) -> HistoryPage:
        result = await self._request(
            "session/history",
            HistoryQueryParams(
                session_id=self._require_session(), cursor=cursor, limit=limit, direction=direction,
            ),
        )
        parsed = HistoryResult.model_validate(result)
        return HistoryPage(
            segments=[ModelMessagesTypeAdapter.validate_python(segment) for segment in parsed.segments],
            first_segment_index=parsed.first_segment_index,
            next_cursor=parsed.next_cursor,
            previous_cursor=parsed.previous_cursor,
            has_more=parsed.has_more,
        )

    async def set_model(self, model: str) -> None:
        await self._request("session/set_model", SetModelParams(session_id=self._require_session(), model=model))

    async def start_turn(self, text: str) -> None:
        await self._request("turn/start", TurnStartParams(session_id=self._require_session(), input=text))
        self._turn_active = True

    async def cancel(self) -> None:
        await self._request("turn/cancel", SessionParams(session_id=self._require_session()))

    async def events(self) -> AsyncIterator[ServerEvent]:
        while True:
            event = await self._events.get()
            if isinstance(event, TurnFinished):
                self._turn_active = False
            yield event

    # ---- 服务器来信 ----

    async def _on_request(self, method: str, params: dict) -> dict:
        if method == "approval/request":
            approved = await self._on_approval(ApprovalRequestParams.model_validate(params))
            return ApprovalResult(approved=approved).model_dump()
        if method == "question/request":
            answer = await self._on_question(QuestionRequestParams.model_validate(params))
            return QuestionResult(answer=answer).model_dump()
        raise JsonRpcError(METHOD_NOT_FOUND, f"未知方法: {method}")

    async def _on_notification(self, method: str, params: dict) -> None:
        if method != "session/event":
            return
        p = SessionEventParams.model_validate(params)
        if self.session_id is not None and p.session_id != self.session_id:
            return  # 非当前会话的事件（如同一连接上的旧会话）
        try:
            event = _EVENT.validate_python(p.event)
        except ValidationError:
            logger.warning("跳过无法识别的事件: {}", p.event.get("kind"))
            return
        await self._events.put(event)

    # ---- 工具 ----

    async def _request(self, method: str, params) -> dict:
        assert self._connection is not None, "connect() 未被调用"
        return await self._connection.send_request(method, params)

    def _bind_session(self, result: dict) -> str:
        session_id = SessionResult.model_validate(result).session_id
        assert session_id is not None
        self.session_id = session_id
        return session_id

    def _require_session(self) -> str:
        assert self.session_id is not None, "尚无会话"
        return self.session_id

    # ---- 默认传输：stdio 子进程 ----

    def _spawn_stdio(self) -> Transport:
        proc = subprocess.Popen(
            [sys.executable, "-m", "spring_harness.entrypoints.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        inbox: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        # Windows 控制台没有可靠的异步管道，读线挪线程
        def reader() -> None:
            assert proc.stdout is not None
            for raw in proc.stdout:
                loop.call_soon_threadsafe(inbox.put_nowait, raw.decode("utf-8", "replace"))
            loop.call_soon_threadsafe(inbox.put_nowait, None)  # EOF

        threading.Thread(target=reader, daemon=True).start()

        async def read_line() -> str | None:
            return await inbox.get()

        def write_sync(line: str) -> None:
            assert proc.stdin is not None
            proc.stdin.write(line.encode("utf-8") + b"\n")
            proc.stdin.flush()

        async def write_line(line: str) -> None:
            # 大 payload（如历史回拉响应外的超大请求）防管道写满阻塞事件循环
            await asyncio.to_thread(write_sync, line)

        return read_line, write_line, proc.terminate
