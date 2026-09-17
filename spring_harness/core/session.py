import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from pydantic_ai import (
    Agent,
    CancellationToken,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    RunCancelled,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.messages import INTERRUPTED_TOOL_RETURN_CONTENT

from spring_harness.core.agent.deps import CodingAgentDeps
from spring_harness.core.approval import run_with_approval
from spring_harness.core.history import HistoryDirection, HistoryPage
from spring_harness.core.session_store import SessionStore
from spring_harness.core.stream.adapter import AgentEventAdapter
from spring_harness.core.stream.emit import EventEmitter, PendingRequests
from spring_harness.core.stream.events import (
    CompactionNotice,
    PlanUpdated,
    ServerEvent,
    TeachingUpdated,
    TurnFinished,
)


def _settle_interrupted_tool_calls(messages: list[ModelMessage]) -> list[ModelMessage]:
    """给没跑出结果的工具调用补 outcome='interrupted' 的合成返回。

    工具执行中途被取消时，历史末尾的 ModelResponse 里会留下没有 ToolReturnPart 的
    ToolCallPart；response 本身是完整的（state 不是 interrupted），pydantic-ai 不会
    自动补，带着它发起下一轮会被 UserError 拒绝（unprocessed tool calls）。这里补上
    与库自带修复一致的合成返回，历史即可续。
    """
    answered = {
        part.tool_call_id
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart | RetryPromptPart)
    }
    dangling = [
        part
        for message in messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart) and part.tool_call_id not in answered
    ]
    if not dangling:
        return messages
    return [
        *messages,
        ModelRequest(parts=[
            ToolReturnPart(
                tool_name=part.tool_name,
                content=INTERRUPTED_TOOL_RETURN_CONTENT,
                tool_call_id=part.tool_call_id,
                outcome="interrupted",
            )
            for part in dangling
        ]),
    ]


class HarnessSession:
    def __init__(
        self,
        workspace: str | Path,
        *,
        agent: Agent[Any, Any] | None = None,
        store: SessionStore | None = None,
        deps: CodingAgentDeps | None = None,
        model_name: str | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self._store = store or SessionStore.create(self.workspace)
        self.session_id = self._store.session_id
        self._model_name = model_name
        self._agent = agent
        self._deps = deps or CodingAgentDeps.create_default(self.workspace)
        self._history: list[ModelMessage] = []
        self._history_loaded = store is None
        self._history_lock = asyncio.Lock()
        self._queue: asyncio.Queue[ServerEvent] = asyncio.Queue()
        self._requests = PendingRequests(self._emit)
        self._cancel_token: CancellationToken | None = None
        self._busy = False
        self._closed = False
        self._turn_task: asyncio.Task | None = None

    async def events(self) -> AsyncIterator[ServerEvent]:
        while True:
            yield await self._queue.get()

    async def run_turn(self, text: str) -> None:
        if self._closed:
            raise RuntimeError("会话已关闭")
        if self._busy:
            raise RuntimeError("上一轮还没结束")
        self._busy = True
        self._turn_task = asyncio.current_task()
        finished = TurnFinished()
        messages: list[ModelMessage] | None = None
        allow_rewrite = False
        try:
            self._cancel_token = CancellationToken()
            if not self._history_loaded:
                await self.query_history()
            # 愈合旧版本取消轮留下的中断尾（悬挂工具调用），否则本轮直接 UserError
            self._history = _settle_interrupted_tool_calls(self._history)
            agent = await self._in_thread(self._ensure_agent)
            adapter = AgentEventAdapter(EventEmitter(self._emit_progress))
            result = await run_with_approval(
                agent, text, adapter,
                ask=self._requests.ask, ask_question=self._requests.ask_question,
                deps=self._deps, message_history=self._history,
                cancellation_token=self._cancel_token,
            )
            messages = result.all_messages()
            allow_rewrite = True
        except RunCancelled as e:
            messages = _settle_interrupted_tool_calls(e.all_messages())
            allow_rewrite = True
            finished.cancelled = True
        except asyncio.CancelledError as e:
            finished.cancelled = True
            if self._turn_task is not None and self._turn_task.cancelling():
                raise
            # 外部取消（取消 token）也可能挂着运行状态：能恢复就同样补合成返回
            cancelled_run = RunCancelled.from_cancellation(e)
            if cancelled_run is not None:
                messages = _settle_interrupted_tool_calls(cancelled_run.all_messages())
                allow_rewrite = True
        except Exception as e:  # noqa: BLE001
            finished.error = f"{type(e).__name__}: {e}"
        finally:
            try:
                if self._history_loaded:
                    async with self._history_lock:
                        await self._in_thread(
                            self._persist,
                            messages if messages is not None else self._deps.last_messages,
                            allow_rewrite=allow_rewrite,
                        )
            except asyncio.CancelledError:
                finished.cancelled = True
                raise
            except Exception as e:  # noqa: BLE001
                error = f"{type(e).__name__}: {e}"
                finished.error = f"{finished.error}; {error}" if finished.error else error
            finally:
                self._requests.cancel_all()
                self._cancel_token = None
                self._busy = False
                self._turn_task = None
                self._queue.put_nowait(finished)

    def respond(self, request_id: str, value: Any) -> None:
        self._requests.resolve(request_id, value)

    def cancel(self) -> None:
        if self._cancel_token is not None:
            self._cancel_token.cancel()
        self._requests.cancel_all()

    async def close(self) -> None:
        self._closed = True
        self.cancel()
        task = self._turn_task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._in_thread(self._deps.monitor.close)

    @classmethod
    def resume_last(cls, workspace: str | Path, **kwargs: Any) -> HarnessSession | None:
        sessions = SessionStore.list_sessions(Path(workspace).resolve())
        if not sessions:
            return None
        return cls(workspace, store=sessions[-1][0], **kwargs)

    async def load_history(self) -> list[list[ModelMessage]]:
        return (await self.query_history()).segments

    async def query_history(
        self,
        cursor: str | None = None,
        limit: int | None = None,
        direction: HistoryDirection = "forward",
    ) -> HistoryPage:
        async with self._history_lock:
            messages, page = await self._in_thread(self._store.query_history, cursor, limit, direction)
            if not self._history_loaded:
                self._history = messages
                self._history_loaded = True
            return page

    def set_model(self, model_name: str) -> None:
        self._model_name = model_name
        self._agent = None

    @property
    def history(self) -> list[ModelMessage]:
        return self._history

    @property
    def busy(self) -> bool:
        return self._busy

    async def _emit(self, event: ServerEvent) -> None:
        await self._queue.put(event)

    async def _emit_progress(self, event: ServerEvent) -> None:
        if not isinstance(event, TurnFinished):
            await self._emit(event)

    @staticmethod
    async def _in_thread(function, *args, **kwargs):
        task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
            except Exception:  # noqa: BLE001
                break
        if cancelled:
            if not task.cancelled():
                task.exception()
            raise asyncio.CancelledError
        return task.result()

    def _ensure_agent(self) -> Agent[Any, Any]:
        if self._agent is None:
            from spring_harness.core.agent.agent import create_agent

            self._agent = create_agent(
                self.workspace,
                model_name=self._model_name,
                session_id=self.session_id,
                plan_on_change=lambda items: self._emit(
                    PlanUpdated(items=[i.model_dump() for i in items])),
                teach_on_change=lambda unit: self._emit(
                    TeachingUpdated(unit=unit.model_dump())),
                compact_on_change=lambda dropped, before, after: self._emit(
                    CompactionNotice(dropped=dropped, before=before, after=after)),
            )
        return self._agent

    def _persist(self, messages: list[ModelMessage], *, allow_rewrite: bool = False) -> None:
        if self._save_delta(messages, allow_rewrite=allow_rewrite):
            self._history = messages

    def _save_delta(self, messages: list[ModelMessage], *, allow_rewrite: bool = False) -> bool:
        base = len(self._history)
        if len(messages) > base and messages[:base] == self._history:
            self._store.append(messages[base:])
            return True
        if allow_rewrite and messages != self._history:
            self._store.append_rewritten(messages)
            return True
        return False
