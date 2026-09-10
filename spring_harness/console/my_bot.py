import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, ClassVar

from pydantic_ai import (
    Agent,
    CancellationToken,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    RunCancelled,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from textual.binding import Binding
from textual.worker import Worker

from spring_harness.capabilities.planning import load_plan_items
from spring_harness.capabilities.teaching import teaching_store_for
from spring_harness.console.approval import run_with_approval
from spring_harness.console.cli_sink import CliSink
from spring_harness.console.cli_ui import ModelSelectModal
from spring_harness.console.cli_ui.app import CliApp
from spring_harness.console.cli_ui.modal import SessionSelectModal
from spring_harness.console.cli_ui.widgets import ChatScroll, WelcomeBox
from spring_harness.console.renderer import EventStreamRenderer, make_diff
from spring_harness.core.agent.agent import create_agent
from spring_harness.core.agent.deps import CodingAgentDeps
from spring_harness.core.config.settings import config
from spring_harness.core.services.session_store import (
    SessionStore,
    format_local_time,
)


def _restore_boundary(
    segments: list[list[ModelMessage]], max_rounds: int
) -> tuple[int, int, int]:
    """倒数第 max_rounds 轮在 segments 里的位置：(segment 下标, message 下标, 跳过的轮数)。

    一轮以带文本 UserPromptPart 的 ModelRequest 起算；轮数不超 max_rounds 时
    返回 (0, 0, 0) 即从头重放。
    """
    positions: list[tuple[int, int]] = []
    for si, messages in enumerate(segments):
        for mi, msg in enumerate(messages):
            if isinstance(msg, ModelRequest) and any(
                isinstance(p, UserPromptPart) and isinstance(p.content, str)
                for p in msg.parts
            ):
                positions.append((si, mi))
    if len(positions) <= max_rounds:
        return 0, 0, 0
    si, mi = positions[-max_rounds]
    return si, mi, len(positions) - max_rounds


class MyBot(CliApp):
    BINDINGS: ClassVar[list] = [
        # 非 priority：命令下拉/弹窗的 Esc 先消费（关下拉、拒弹窗），其余情况才中断运行
        Binding("escape", "interrupt_run", "中断运行", show=False),
    ]

    def __init__(self, *args, resume_last: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._busy = False
        self._cancel_token: CancellationToken | None = None  # 当前轮的取消令牌，Ctrl+C 触发
        self._message_history: list[ModelMessage] = []
        self._session_deps = CodingAgentDeps.create_default(Path.cwd())
        # 预建教学 store（主线程），避免与 executor 里的 create_agent 竞态创建
        teaching_store_for(Path.cwd())
        self._agent = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._model_id = config.default_model

        sessions = SessionStore.list_sessions(Path.cwd())
        if resume_last and sessions:
            self._store, _ = sessions[-1]
        else:
            self._store = SessionStore.create(Path.cwd())
        # 会话文件不在 __init__ 解析：pydantic 逐行校验整个 JSONL，长会话
        # 秒级，发生在 Textual 启动前就是"启动黑屏"的大头；on_mount 里起
        # 后台 worker 恢复，首帧先亮，历史边解析边进场
        self._resume_pending = resume_last and bool(sessions)
        self._restore_worker: Worker[None] | None = None
        self._sync_session_id()
        self._rebuild_agent()

    def _sync_session_id(self) -> None:
        """会话 id 取 rollout 文件名末尾的完整 uuid，显示在欢迎框。"""
        stem = self._store.path.stem
        self.session_id = f"session_{stem[-36:]}"

    def _rebuild_agent(self, model_name: str | None = None) -> None:
        """后台重建 agent：模型或会话切换后调用；session_id 决定 plan 归属。"""
        self._agent = None
        self._executor_future = self._executor.submit(
            create_agent, Path.cwd(),
            model_name=model_name or self._model_id,
            session_id=self._store.path.stem,
            plan_on_change=self._on_plan_change,
            teach_on_change=self._on_teach_change,
            compact_on_change=self._on_compact,
        )

    async def _on_plan_change(self, items: list) -> None:
        """计划变更回调：在 agent 运行的事件循环里被 store 包装层 await。"""
        await self.show_plan(items)

    async def _on_teach_change(self, unit) -> None:
        """教学单元变更回调：与计划同路，在 agent 运行的事件循环里被 await。"""
        await self.show_teaching(unit)

    async def _on_compact(self, dropped: int, before: int, after: int) -> None:
        """压缩完成回调：对话流里插一行信息"""
        await self.show_system(
            f"上下文已压缩：折叠 {dropped} 条旧消息（约 {before // 1000}k → {after // 1000}k tokens）\n"
        )

    async def on_mount(self) -> None:
        super().on_mount()
        if self._resume_pending:
            self._restore_worker = self.run_worker(self._restore_session())

    async def _restore_session(self) -> None:
        """后台恢复会话：文件解析挪线程（CPU 密集，别按住事件循环）。"""
        self._busy = True  # 恢复期间挡住 /resume /new 等命令
        self.set_working("restoring")  # 加载指示（kimi-cli 的 "Restoring conversation..." 同款）
        try:
            messages, segments = await asyncio.to_thread(self._store.load_for_resume)
            self._message_history = messages
            await self._rebuild_chat(segments)
        finally:
            self._busy = False
            self.set_working(None)

    async def _get_agent(self) -> Agent[Any, Any]:
        if self._agent is None:
            self._agent = await asyncio.wrap_future(self._executor_future)
        return self._agent

    def action_interrupt_run(self) -> None:
        """Esc：取消当前 run（token.cancel 线程安全，不阻塞事件循环）；空闲时无操作。"""
        if self._busy and self._cancel_token is not None:
            self._cancel_token.cancel()
            self.set_working("cancelling")

    async def handle_input(self, text: str) -> None:
        restore_worker = self._restore_worker
        if restore_worker is not None:
            # 恢复还在后台跑：等它落完再开跑，保证模型拿到完整历史
            self._restore_worker = None
            try:
                await restore_worker.wait()
            except Exception as e:
                await self.show_system(f"❌ 恢复会话失败：{e}")
        sink = CliSink(self)
        renderer = EventStreamRenderer(sink)

        async def ask_with_preview(call: ToolCallPart) -> bool:
            # 编辑类工具把改动 diff 带进审批弹窗
            return await self.ask_approval(call, diff=make_diff(call.tool_name, call.args))

        async def ask_question_ui(args: dict[str, Any]) -> str | None:
            return await self.ask_question(
                question=args["question"],
                options=args.get("options"),
                allow_custom=args.get("allow_custom", True),
            )


        self._busy = True
        self._cancel_token = CancellationToken()
        try:
            result = await run_with_approval(
                await self._get_agent(),
                text,
                renderer,
                ask_with_preview,
                ask_question_ui,
                deps=self._session_deps,
                message_history=self._message_history,
                cancellation_token=self._cancel_token,
            )
        except RunCancelled as e:
            # Esc 中断：快照含本轮已完成的工具结果，落盘并接管历史，
            # 下一条输入带着它续跑，断掉的工具调用由 pydantic-ai 自动修补
            self._save_delta(e.all_messages(), allow_rewrite=True)
            self._message_history = e.all_messages()
            await self.show_system("已中断（Esc），可继续输入")
            return
        except BaseException:
            # 运行中途异常终止（模型/工具报错、worker 被取消）时，把钩子快照里
            if self._save_delta(self._session_deps.last_messages):
                self._message_history = self._session_deps.last_messages
            raise
        finally:
            self._cancel_token = None
            self._busy = False

        # 带审批的轮次会跑多次 agent.run，result.new_messages() 只含最后一次 run 的
        # 增量；相对轮前历史取差才能把整轮落全
        self._save_delta(result.all_messages(), allow_rewrite=True)
        self._message_history = result.all_messages()

    def _save_delta(self, messages: list[ModelMessage], *, allow_rewrite: bool = False) -> bool:
        """把 messages 相对已存历史的增量追加到会话文件，返回是否有内容落盘。

        messages 通常以当前 _message_history 为前缀（运行结果和
        before_model_request 钩子写入 deps.last_messages 的快照都满足），
        此时只追加增量；对不上说明是上一轮残留的过期快照，直接忽略，
        避免把会话文件写坏。

        allow_rewrite=True 只给正常轮次的运行结果用：前缀对不上意味着历史被
        压缩/消息合并合法改写（摘要、回执都只在改写后的历史里），追加
        history_rewrite 标记和新基线；异常路径的钩子快照可能是过期的，
        不传，防止写回去缩。
        """
        base = len(self._message_history)
        if len(messages) > base and messages[:base] == self._message_history:
            self._store.append(messages[base:])
            return True
        if allow_rewrite and messages != self._message_history:
            self._store.append_rewritten(messages)
            return True
        return False

    async def handle_command(self, command: str) -> None:
        if self._busy:
            await self.show_system("运行中，不能执行命令")
            return

        name, _, arg = command.partition(" ")
        arg = arg.strip()

        if name == "new":
            self._store = SessionStore.create(Path.cwd())
            self._sync_session_id()
            self._rebuild_agent()
            self._message_history = []
            await self._rebuild_chat([])
            await self.show_system("已开始新会话")
            return

        if name == "resume":
            sessions = SessionStore.list_sessions(Path.cwd())
            if not sessions:
                await self.show_system("当前项目没有历史会话")
                return
            if not arg:
                # push_screen_wait 必须在 worker 里调（textual 硬性限制），弹窗流程包一层
                self.run_worker(self._resume_via_modal(sessions))
            else:
                n = int(arg) if arg.isdigit() else -1
                if not 1 <= n <= len(sessions):
                    await self.show_system(f"无效编号：{arg}")
                    return
                await self._switch_to(sessions[n - 1][0])
            return

        if name == "model":
            self.run_worker(self._select_model_via_modal())
            return

        await super().handle_command(command)

    async def _switch_to(self, store: SessionStore) -> None:
        self._busy = True  # 切换期间挡住其它命令，避免并发重建
        self.set_working("restoring")
        try:
            self._store = store
            self._sync_session_id()
            self._rebuild_agent()
            # 单次解析（挪线程）：两个 load 分开调会把整个 JSONL 各解析一遍
            self._message_history, segments = await asyncio.to_thread(store.load_for_resume)
            await self._rebuild_chat(segments)
            await self.show_system("已切换会话")
        finally:
            self._busy = False
            self.set_working(None)

    async def _resume_via_modal(self, sessions: list[tuple[SessionStore, dict]]) -> None:
        ordered = list(reversed(sessions))
        current_id = self._store.path.stem
        labels = [
            f"{format_local_time(meta.get('updated_at') or meta['created_at'])}  {meta.get('title') or '(空会话)'}"
            for store, meta in ordered
        ]
        current = next(
            (i for i, (store, _) in enumerate(ordered) if store.path.stem == current_id),
            None,
        )
        picked = await self.push_screen_wait(SessionSelectModal(labels, current=current))
        if picked is not None:
            await self._switch_to(sessions[len(sessions) - 1 - picked][0])

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
        self._rebuild_agent(picked)

        model_cfg = config.get_model(picked)
        if model_cfg is None:
            await self.show_system(f"模型配置不存在: {picked}")
            return
        self.set_model(model_cfg.display_name, model_cfg.max_context_size)
        await self.show_system(f"已切换到 {model_cfg.display_name}" + ("" if persist else "（仅本次会话）"))


    async def _rebuild_chat(self, segments: list[list[ModelMessage]]) -> None:
        # 双缓冲重建（kimi-code 的 switchToSession 思路：旧内容保持到最后一刻，
        # 清旧与灌新背靠背、中间无空窗）：新 ChatScroll 隐藏挂载，历史重放进
        # 新容器，旧容器全程可见；重放完先把锚挂上，再同一帧内"旧下架+新亮相"，
        # 用户看到的第一帧就是落在底部的最终状态——启动恢复和 /resume 切换
        # 都不再有"旧内容一闪 → 空白 → 新内容"的跳变
        old_scroll = self._chat_scroll
        assert old_scroll is not None
        new_scroll = ChatScroll()
        new_scroll.styles.display = "none"
        await self.mount(new_scroll, before=old_scroll)
        self._chat_scroll = new_scroll  # 此后 self._scroll / show_* 全部指向新容器
        try:
            self._plan_widget = None  # 旧 PlanMessage 随旧容器一起摘除
            self._teach_widget = None  # 同理
            await new_scroll.mount(
                WelcomeBox(
                    title=self.title_text, model=self.model,
                    version=self.version, session=self.session_id,
                )
            )

            # 只重放最近 MAX_RENDERED_ROUNDS 轮
            start_si, start_mi, dropped = _restore_boundary(segments, self.MAX_RENDERED_ROUNDS)
            if dropped:
                await self.show_system(
                    f"── 更早的 {dropped} 轮交互未渲染（仅保留最近 {self.MAX_RENDERED_ROUNDS} 轮）──"
                )

            pending: dict[str, ToolCallPart] = {}

            for index, messages in enumerate(segments):
                if index < start_si:
                    continue
                if index > start_si:
                    await self.show_system("── 上下文已压缩，以上内容已压缩为摘要 ──")
                for msg in (messages[start_mi:] if index == start_si else messages):
                    if isinstance(msg, ModelRequest):
                        for part in msg.parts:
                            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                                await self.show_user(part.content)
                            elif isinstance(part, ToolReturnPart | RetryPromptPart) and part.tool_call_id:
                                call = pending.pop(part.tool_call_id, None)
                                if call is not None:
                                    await self.show_tool_call(
                                        call.tool_name,
                                        args=str(call.args),
                                        result=str(part.content)[:500],
                                    )
                    elif isinstance(msg, ModelResponse):
                        texts = [p for p in msg.parts if isinstance(p, TextPart)]
                        if texts:
                            handle = await self.start_assistant()
                            # 重放不是流：一次性整段写入，解析在线程池
                            await handle.set_answer_full("".join(t.content for t in texts))
                            await handle.finish()
                        for p in msg.parts:
                            if isinstance(p, ToolCallPart):
                                pending[p.tool_call_id] = p

            for call in pending.values():
                await self.show_tool_call(call.tool_name, args=str(call.args))

            # 该会话持久化的计划也一并重建到末尾
            items = await load_plan_items(self._store.path.stem)
            if items:
                await self.show_plan(items)

            # 工作区里活跃的教学单元（跨会话存活）同样重建到末尾
            unit = await teaching_store_for(Path.cwd()).get_active()
            if unit:
                await self.show_teaching(unit)

            # 亮相前先锚定：display 恢复后的首次重排，合成器直接把容器定在底部
            self._scroll.anchor()
        finally:
            # 同一帧内完成交换：先下架旧容器再亮新容器（两个 1fr 容器
            # 并存会平分高度；先摘旧则中间有一帧全空），最后再真正摘除
            old_scroll.styles.display = "none"
            new_scroll.styles.display = "block"
            await old_scroll.remove()
