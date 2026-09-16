import asyncio
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

from pydantic_ai import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai_harness.planning import PlanItem
from textual.binding import Binding
from textual.containers import Vertical
from textual.widget import Widget
from textual.worker import Worker, WorkerCancelled, WorkerFailed

from spring_harness.capabilities.planning import load_plan_items
from spring_harness.capabilities.teaching import TeachingUnit, teaching_store_for
from spring_harness.console.cli_sink import CliSink
from spring_harness.console.cli_ui import ModelSelectModal
from spring_harness.console.cli_ui.app import AssistantHandle, CliApp
from spring_harness.console.cli_ui.inputs import HistoryInput
from spring_harness.console.cli_ui.modal import SessionSelectModal
from spring_harness.console.cli_ui.widgets import (
    AssistantMessage,
    PlanMessage,
    SystemMessage,
    TeachingMessage,
    ToolCallMessage,
    UserMessage,
    WelcomeBox,
)
from spring_harness.core.config.settings import config
from spring_harness.core.history import HistoryPage
from spring_harness.core.hooks.model import is_auto_injected_message
from spring_harness.core.rpc.client import AppClient
from spring_harness.core.rpc.connection import JsonRpcError
from spring_harness.core.rpc.schema import (
    ApprovalRequestParams,
    QuestionRequestParams,
    SessionSummary,
)
from spring_harness.core.session_store import format_local_time
from spring_harness.core.stream.events import (
    BackgroundTaskFinished,
    BackgroundTaskStarted,
    CompactionNotice,
    PlanUpdated,
    TeachingUpdated,
    TextDelta,
    ThinkingDelta,
    ToolArgsDelta,
    ToolCallStarted,
    ToolDiff,
    ToolFinished,
    ToolPending,
    TurnFinished,
    UsageUpdated,
)
from spring_harness.core.stream.sink import ToolCallSink


class ConsoleClient(CliApp):
    HISTORY_PAGE_SIZE: ClassVar[int] = 20
    MAX_RENDERED_ROUNDS: ClassVar[int] = 10

    BINDINGS: ClassVar[list] = [
        Binding("escape", "interrupt_run", "中断运行", show=False),
    ]

    def __init__(self, *args, resume_last: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._busy = False
        self._initialized = False
        self._model_id = config.default_model
        self._client = AppClient(
            Path.cwd(),
            on_approval=self._ask_approval_in_worker,
            on_question=self._ask_question_in_worker,
        )
        self._resume_last = resume_last
        self.session_id = ""
        self._session_worker: Worker[None] | None = None
        self._panel_worker: Worker[None] | None = None
        # 泵走裸 task 而不是 Worker：它常驻整个连接生命周期，进 Worker 登记表会让
        # workers.wait_for_complete()（/new、/resume 的等待点）永远等不到
        self._pump_task: asyncio.Task[None] | None = None
        self._turn_done: asyncio.Event | None = None  # 当前用户轮的收尾信号，由泵在 TurnFinished 时置位
        self._history_generation = 0

    def on_mount(self) -> None:
        self._begin_session_setup("connecting")
        self._session_worker = self.run_worker(self._initialize_session())

    async def _initialize_session(self) -> None:
        try:
            await self._client.connect()
            session_id = None
            if self._resume_last:
                self.set_working("loading_sessions")
                session_id = await self._client.resume_last(model=self._model_id)
            resumed = session_id is not None
            if session_id is None:
                self.set_working("creating")
                session_id = await self._client.new_session(model=self._model_id)
            self._sync_session_id(session_id)
            if resumed:
                await self._restore_session()
            self._initialized = True
            # 事件泵长驻：催醒轮等系统轮次在用户无输入时也会产生事件，按轮起泵会把它们吞到下次输入
            self._pump_task = asyncio.create_task(self._pump_events())
        except Exception as e:  # noqa: BLE001
            await self.show_system(f"❌ 初始化会话失败：{e}")
        finally:
            self._end_session_setup()

    async def _cancel_worker(self, worker: Worker[None] | None) -> None:
        if worker is None:
            return
        if not worker.is_finished and not worker.is_cancelled:
            worker.cancel()
        try:
            await worker.wait()
        except (WorkerCancelled, WorkerFailed):
            pass

    async def on_unmount(self) -> None:
        self._initialized = False
        self._history_generation += 1
        pump_task = self._pump_task
        if pump_task is not None:
            pump_task.cancel()
        try:
            await self._cancel_worker(self._session_worker)
            await self._cancel_worker(self._panel_worker)
            if pump_task is not None:
                await asyncio.gather(pump_task, return_exceptions=True)
        finally:
            self._session_worker = self._panel_worker = self._pump_task = None
            self._busy = False
            await self._client.close()

    def _begin_session_setup(self, state: str) -> None:
        self._initialized = False
        self._busy = True
        self._history_generation += 1
        if self._panel_worker is not None and not self._panel_worker.is_finished:
            self._panel_worker.cancel()
        self.query_one("#user-input", HistoryInput).disabled = True
        self.set_working(state)

    def _end_session_setup(self) -> None:
        self._busy = False
        if self.is_running:
            self.set_working(None)
            input_widget = self.query_one("#user-input", HistoryInput)
            input_widget.disabled = not self._initialized
            if self._initialized:
                input_widget.focus()

    def _sync_session_id(self, session_id: str) -> None:
        self.session_id = f"session_{session_id[-36:]}"
        self._scroll.query_one(WelcomeBox).set_session(self.session_id)

    async def _restore_session(self) -> None:
        self.set_working("restoring")
        generation = self._history_generation
        page = await self._recent_history()
        if generation != self._history_generation or not self.is_running:
            raise asyncio.CancelledError
        await self._rebuild_chat(page)
        self._panel_worker = self.run_worker(self._restore_panels(generation))

    async def _recent_history(self) -> HistoryPage:
        generation = self._history_generation
        segments: dict[int, list[ModelMessage]] = {}
        cursor = None
        seen: set[str] = set()
        rounds = 0
        while True:
            page = await self._client.query_history(
                cursor=cursor, limit=self.HISTORY_PAGE_SIZE, direction="backward",
            )
            if generation != self._history_generation or not self.is_running:
                raise asyncio.CancelledError
            if page.previous_cursor is not None and (
                page.previous_cursor in seen or not any(page.segments)
            ):
                raise ValueError("历史分页未前进")
            first = page.first_segment_index
            if page.segments and first is None:
                raise ValueError("历史分页缺少段位置")
            if first is not None:
                for offset, messages in enumerate(page.segments):
                    segments.setdefault(first + offset, [])[:0] = messages
                for offset in reversed(range(len(page.segments))):
                    messages = page.segments[offset]
                    for index in reversed(range(len(messages))):
                        message = messages[index]
                        if not isinstance(message, ModelRequest) or is_auto_injected_message(message):
                            continue
                        for part_index in reversed(range(len(message.parts))):
                            part = message.parts[part_index]
                            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                                rounds += 1
                                if rounds == self.MAX_RENDERED_ROUNDS:
                                    start = first + offset
                                    segments[start] = segments[start][index:]
                                    segments[start][0] = replace(message, parts=message.parts[part_index:])
                                    return HistoryPage(
                                        segments=[segments.get(i, []) for i in range(start, max(segments) + 1)],
                                        first_segment_index=start,
                                    )
            cursor = page.previous_cursor
            if cursor is None:
                return HistoryPage(
                    segments=[segments.get(i, []) for i in range(min(segments), max(segments) + 1)]
                    if segments else [],
                    first_segment_index=min(segments) if segments else None,
                )
            seen.add(cursor)

    # ---- 审批/提问：服务器请求回调 ----

    async def _ask_approval_in_worker(self, p: ApprovalRequestParams) -> bool:
        call = ToolCallPart(tool_name=p.tool_name, args=p.args, tool_call_id=p.tool_call_id)
        worker = self.run_worker(self.ask_approval(call, diff=p.diff))
        return await worker.wait()

    async def _ask_question_in_worker(self, p: QuestionRequestParams) -> str | None:
        worker = self.run_worker(
            self.ask_question(question=p.question, options=p.options, allow_custom=p.allow_custom)
        )
        return await worker.wait()

    # ---- 轮次 ----

    def action_interrupt_run(self) -> None:
        if (
            self._initialized and self._busy
            and (self._session_worker is None or self._session_worker.is_finished)
        ):
            self.run_worker(self._client.cancel())
            self.set_working("cancelling")

    async def _wait_for_session(self, worker: Worker[None]) -> bool:
        try:
            await worker.wait()
        except WorkerCancelled:
            return False
        except WorkerFailed as e:
            if self.is_running:
                await self.show_system(f"❌ 会话准备失败：{e}")
            return False
        return True

    async def handle_input(self, text: str) -> None:
        session_worker = self._session_worker
        if session_worker is not None and not await asyncio.shield(self._wait_for_session(session_worker)):
            return

        if not self.is_running:
            return
        if not self._initialized:
            await self.show_system("会话尚未就绪，不能发送消息")
            return
        if self._busy:
            await self.show_system("运行中，不能发送消息")
            return

        self._busy = True
        turn_done = self._turn_done = asyncio.Event()
        try:
            await self._cancel_worker(self._panel_worker)
            try:
                await self._client.start_turn(text)
            except JsonRpcError as e:
                self._busy = False
                await self.show_system(f"❌ {e}")
                return
            self.set_working("idle")  # 消息已发出、内容未到达
            # 轮次事件由长驻泵渲染；TurnFinished 时泵复位 _busy 并置位 turn_done
            await turn_done.wait()
        finally:
            if self._turn_done is turn_done:
                self._turn_done = None

    async def _pump_events(self) -> None:
        """事件泵：一条连接一条长驻（对 rpc 服务器 _pump 的镜像），TurnFinished 只收尾不退出。"""
        # sink 每轮一个，首个内容事件到达时才建：CliSink 创建即把 WorkingLine 置为
        # idle（"消息已发出"），启动时就建会让空闲中的状态栏一直显示 idle
        sink: CliSink | None = None
        tool_sinks: dict[str, ToolCallSink] = {}
        try:
            async for event in self._client.events():
                match event:
                    case ThinkingDelta(text=t):
                        sink = sink or CliSink(self)
                        await sink.write_thinking(t)
                    case TextDelta(text=t):
                        sink = sink or CliSink(self)
                        await sink.write_answer(t)
                    case ToolCallStarted(tool_call_id=i, tool_name=n):
                        sink = sink or CliSink(self)
                        tool_sinks[i] = await sink.start_tool_call(n, i)
                    case ToolArgsDelta(tool_call_id=i, args_chunk=c):
                        if (tool := tool_sinks.get(i)) is not None:
                            await tool.write_args(c)
                    case ToolDiff(tool_call_id=i, diff=d):
                        if (tool := tool_sinks.get(i)) is not None:
                            await tool.show_diff(d)
                    case ToolPending(tool_call_id=i, label=label):
                        if (tool := tool_sinks.get(i)) is not None:
                            await tool.show_pending(label)
                    case ToolFinished(tool_call_id=i, result=r, is_error=is_err):
                        if (tool := tool_sinks.get(i)) is not None:
                            await tool.show_result(r, is_err)
                    case UsageUpdated(context_tokens=tokens):
                        self.update_context(tokens)
                    case PlanUpdated(items=items):
                        await self.show_plan([PlanItem(**d) for d in items])
                    case TeachingUpdated(unit=u):
                        await self.show_teaching(TeachingUnit(**u))
                    case CompactionNotice(dropped=d, before=before, after=after):
                        await self.show_system(
                            f"上下文已压缩：折叠 {d} 条旧消息（约 {before // 1000}k → {after // 1000}k tokens）\n"
                        )
                    case BackgroundTaskStarted(task_id=i, tool_name=n):
                        await self.show_system(f"⚙ 后台任务 {i} 已开始（{n}），完成后会自动汇报")
                    case BackgroundTaskFinished(task_id=i, tool_name=n, is_error=is_err, cancelled=cancelled):
                        # 一行简报：完成时刻必定可见（成功时结果内容由催醒轮/当前轮汇报）
                        if cancelled:
                            await self.show_system(f"⚙ 后台任务 {i}（{n}）已取消")
                        elif is_err:
                            await self.show_system(f"⚙ 后台任务 {i}（{n}）出错，详情见后续汇报")
                        else:
                            await self.show_system(f"⚙ 后台任务 {i}（{n}）已完成")
                    case TurnFinished(cancelled=cancelled, error=error, wake=wake):
                        if sink is not None:
                            await sink.finish()
                            sink = None
                        self.set_working(None)
                        tool_sinks.clear()
                        if cancelled and not wake:
                            # 催醒轮被用户输入抢占是常态，静默收尾；只有用户轮的中断才提示
                            await self.show_system("已中断（Esc），可继续输入")
                        elif error is not None:
                            await self.show_system(f"❌ 运行出错：{error}")
                        if not wake:
                            # 只有用户轮占用 _busy、有人等收尾；催醒轮的收尾不动输入状态
                            self._busy = False
                            if self._turn_done is not None:
                                self._turn_done.set()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            if self.is_running:
                await self.show_system(f"❌ 事件流中断：{e}")
        finally:
            # 泵退出（连接断开/卸载）：别让 handle_input 永远等不到收尾
            self._busy = False
            if self._turn_done is not None:
                self._turn_done.set()

    # ---- 命令 ----

    async def handle_command(self, command: str) -> None:
        if self._busy:
            await self.show_system("运行中，不能执行命令")
            return
        if not self._initialized:
            await self.show_system("会话尚未就绪，不能执行命令")
            return

        name, _, arg = command.partition(" ")
        arg = arg.strip()

        if name == "new":
            self._begin_session_setup("creating")
            self._session_worker = self.run_worker(self._change_session())
            await asyncio.shield(self._wait_for_session(self._session_worker))
            return

        if name == "resume":
            self._begin_session_setup("loading_sessions")
            self._session_worker = self.run_worker(self._resume_command(arg))
            await asyncio.shield(self._wait_for_session(self._session_worker))
            return

        if name == "model":
            self.run_worker(self._select_model_via_modal())
            return

        await super().handle_command(command)

    async def _resume_command(self, arg: str) -> None:
        try:
            sessions = await self._client.list_sessions()
            self._initialized = True
            if not sessions:
                await self.show_system("当前项目没有历史会话")
                return
            if not arg:
                self.run_worker(self._resume_via_modal(sessions))
                return
            n = int(arg) if arg.isdigit() else -1
            if not 1 <= n <= len(sessions):
                await self.show_system(f"无效编号：{arg}")
                return
            self._initialized = False
            await self._change_session(sessions[n - 1].session_id)
        except Exception as e:  # noqa: BLE001
            self._initialized = True
            await self.show_system(f"❌ 恢复会话失败：{e}")
        finally:
            self._end_session_setup()

    async def _switch_to(self, session_id: str) -> None:
        if self._busy or not self._initialized:
            await self.show_system("会话尚未就绪或正在运行，不能切换会话")
            return
        self._begin_session_setup("connecting")
        self._session_worker = self.run_worker(self._change_session(session_id))
        await asyncio.shield(self._wait_for_session(self._session_worker))

    async def _change_session(self, session_id: str | None = None) -> None:
        try:
            if session_id is None:
                self.set_working("creating")
                session_id = await self._client.new_session(model=self._model_id)
                self._sync_session_id(session_id)
                await self._clear_chat()
                await self.show_system("已开始新会话")
            else:
                self.set_working("connecting")
                await self._client.attach(session_id, model=self._model_id)
                self._sync_session_id(session_id)
                await self._clear_chat()
                await self._restore_session()
                await self.show_system("已切换会话")
            self._initialized = True
        except Exception as e:  # noqa: BLE001
            await self.show_system(f"❌ 切换会话失败：{e}")
        finally:
            self._end_session_setup()

    async def _resume_via_modal(self, sessions: list[SessionSummary]) -> None:
        ordered = list(reversed(sessions))
        labels = [
            f"{format_local_time(s.updated_at or s.created_at)}  {s.title or '(空会话)'}"
            for s in ordered
        ]
        current = next(
            (i for i, s in enumerate(ordered) if s.session_id == self._client.session_id),
            None,
        )
        picked = await self.push_screen_wait(SessionSelectModal(labels, current=current))
        if picked is not None:
            await self._switch_to(sessions[len(sessions) - 1 - picked].session_id)

    async def _select_model_via_modal(self) -> None:
        models = [(mid, m.display_name, m.provider) for mid, m in config.models.items()]
        result = await self.push_screen_wait(
            ModelSelectModal(models=models, current_model=self._model_id)
        )
        if result is None:
            return
        picked, persist = result   # Enter=True 写回配置；Alt+S=False 仅本次会话
        if persist:
            try:
                config.set_default_model(picked)
            except (OSError, ValueError) as e:
                await self.show_system(f"❌ 写入配置失败：{e}")
                return

        self._model_id = picked
        await self._client.set_model(picked)

        model_cfg = config.get_model(picked)
        if model_cfg is None:
            await self.show_system(f"模型配置不存在: {picked}")
            return
        self.set_model(model_cfg.display_name, model_cfg.max_context_size)
        await self.show_system(f"已切换到 {model_cfg.display_name}" + ("" if persist else "（仅本次会话）"))


    async def _history_paint(self) -> None:
        painted = asyncio.Event()
        self.call_after_refresh(painted.set)
        await painted.wait()

    async def _clear_chat(self) -> None:
        scroll = self._scroll
        await self._cancel_worker(self._panel_worker)
        self._panel_worker = None
        for handle in self._active_handles:
            await handle.finish()
        self._active_handles.clear()
        self._active_tool_calls.clear()

        with self.batch_update():
            scroll.screen.clear_selection()
            self._plan_widget = None
            self._teach_widget = None
            stale = [child for child in scroll.children if not isinstance(child, WelcomeBox)]
            for child in stale:
                child.visible = False
                for descendant in child.query("*"):
                    descendant.visible = False
            await scroll.remove_children(stale)
        scroll.anchor()

    async def _rebuild_chat(self, page: HistoryPage) -> None:
        staging = Vertical()
        staging.styles.display = "none"
        await self.mount(staging)
        try:
            await self._render_history_page(page, staging)
            if not self.is_running:
                raise asyncio.CancelledError
            children = list(staging.children)
            await staging.remove_children(children)
            scroll = self._scroll
            stale = [child for child in scroll.children if not isinstance(child, WelcomeBox)]
            for child in stale:
                child.visible = False
                for descendant in child.query("*"):
                    descendant.visible = False
            scroll.screen.clear_selection()
            with self.batch_update():
                self._plan_widget = None
                self._teach_widget = None
                await scroll.remove_children(stale)
                if children:
                    await scroll.mount(*children)
            scroll.anchor()
        finally:
            await staging.remove()


    async def _restore_panels(self, generation: int) -> None:
        session_id = self._client.session_id
        assert session_id is not None
        try:
            items, unit = await asyncio.gather(
                load_plan_items(session_id), teaching_store_for(Path.cwd()).get_active(),
            )
            if generation != self._history_generation or not self.is_running:
                return
            if items:
                self._plan_widget = PlanMessage(items)
                await self._scroll.mount(self._plan_widget)
            if generation != self._history_generation:
                return
            if unit:
                self._teach_widget = TeachingMessage(unit)
                await self._scroll.mount(self._teach_widget)
        except (OSError, ValueError) as e:
            if generation == self._history_generation and self.is_running:
                self.notify(f"恢复面板失败：{e}", severity="warning")

    async def _render_history_page(self, page: HistoryPage, target: Widget | None = None) -> None:
        if not page.segments:
            return
        scroll = target or self._scroll
        generation = self._history_generation
        created: list[Widget] = []
        tools: set[str] = set()
        calls: dict[str, ToolCallPart] = {}
        results: dict[str, ToolReturnPart | RetryPromptPart] = {}
        for segment in page.segments:
            for message in segment:
                for part in message.parts:
                    if isinstance(part, ToolCallPart):
                        calls[part.tool_call_id] = part
                    elif isinstance(part, ToolReturnPart | RetryPromptPart) and part.tool_call_id:
                        results[part.tool_call_id] = part

        async def mount(widget: Widget) -> None:
            created.append(widget)
            await scroll.mount(widget)

        async def tool(part: ToolCallPart | ToolReturnPart | RetryPromptPart) -> None:
            tool_id = part.tool_call_id
            if not tool_id or tool_id in tools:
                return
            call = calls.get(tool_id)
            result = results.get(tool_id)
            widget = ToolCallMessage(
                call.tool_name if call is not None else part.tool_name or "tool",
                args=str(call.args) if call is not None else "",
                result=str(result.content) if result is not None else None,
            )
            if isinstance(result, RetryPromptPart):
                widget._status = "error"
            tools.add(tool_id)
            await mount(widget)

        try:
            rendered = 0
            for offset, messages in enumerate(page.segments):
                if offset:
                    await mount(SystemMessage(
                        "── 上下文已压缩，以上内容已压缩为摘要 ──", classes="history-boundary",
                    ))
                for message in messages:
                    if generation != self._history_generation:
                        raise asyncio.CancelledError
                    if isinstance(message, ModelRequest):
                        is_file_monitor = is_auto_injected_message(message)
                        for part in message.parts:
                            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                                await mount(UserMessage(part.content, is_file_monitor=is_file_monitor))
                            elif isinstance(part, ToolReturnPart | RetryPromptPart):
                                await tool(part)
                    elif isinstance(message, ModelResponse):
                        text = "".join(part.content for part in message.parts if isinstance(part, TextPart))
                        if text:
                            widget = AssistantMessage(answer=text)
                            await mount(widget)
                            handle = AssistantHandle(widget)
                            await handle.set_answer_full(text)
                            await handle.finish()
                        for part in message.parts:
                            if isinstance(part, ToolCallPart) and part.tool_call_id not in results:
                                await tool(part)
                    rendered += 1
                    if rendered % 4 == 0:
                        await self._history_paint()
            await self._history_paint()
            if generation != self._history_generation:
                raise asyncio.CancelledError
        except BaseException:
            for widget in created:
                widget.visible = False
                for descendant in widget.query("*"):
                    descendant.visible = False
            if scroll.is_attached:
                scroll.screen.clear_selection()
            await scroll.remove_children(created)
            raise
