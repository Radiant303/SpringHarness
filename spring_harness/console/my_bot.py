import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pydantic_ai import (
    Agent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from spring_harness.console.approval import run_with_approval
from spring_harness.console.cli_sink import CliSink
from spring_harness.console.cli_ui import ModelSelectModal
from spring_harness.console.cli_ui.app import CliApp
from spring_harness.console.cli_ui.modal import SessionSelectModal
from spring_harness.console.cli_ui.widgets import WelcomeBox
from spring_harness.console.renderer import EventStreamRenderer, make_diff
from spring_harness.core.agent.agent import create_agent
from spring_harness.core.agent.deps import CodingAgentDeps
from spring_harness.core.config.settings import config
from spring_harness.core.services.session_store import (
    SessionStore,
    format_local_time,
)


class MyBot(CliApp):
    def __init__(self, *args, resume_last: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._busy = False
        self._message_history: list[ModelMessage] = []
        self._session_deps = CodingAgentDeps.create_default(Path.cwd())
        self._agent = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._model_id = config.default_model

        sessions = SessionStore.list_sessions(Path.cwd())
        if resume_last and sessions:
            self._store, _ = sessions[-1]
            self._message_history = self._store.load_messages()
        else:
            self._store = SessionStore.create(Path.cwd())
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
        )

    async def on_mount(self) -> None:
        super().on_mount()
        # --continue 恢复时，把上次会话的内容重放到聊天区，不然屏幕是空的
        if self._message_history:
            await self._rebuild_chat(self._message_history)

    async def _get_agent(self) -> Agent[Any, Any]:
        if self._agent is None:
            self._agent = await asyncio.wrap_future(self._executor_future)
        return self._agent

    async def handle_input(self, text: str) -> None:
        sink = CliSink(self)
        renderer = EventStreamRenderer(sink)

        async def ask_with_preview(call: ToolCallPart) -> bool:
            # 编辑类工具把改动 diff 带进审批弹窗
            return await self.ask_approval(call, diff=make_diff(call.tool_name, call.args))

        self._busy = True
        try:
            result = await run_with_approval(
                await self._get_agent(),
                text,
                renderer,
                ask_with_preview,
                deps=self._session_deps,
                message_history=self._message_history,
            )
        except Exception:
            if self._session_deps.last_messages:
                self._message_history = self._session_deps.last_messages
            raise
        finally:
            self._busy = False

        self._store.append(result.new_messages())
        self._message_history = result.all_messages()

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
        self._store = store
        self._sync_session_id()
        self._rebuild_agent()
        self._message_history = store.load_messages()
        await self._rebuild_chat(self._message_history)
        await self.show_system("已切换会话")

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


    async def _rebuild_chat(self, messages: list[ModelMessage]) -> None:
        await self._scroll.remove_children()
        await self._scroll.mount(
            WelcomeBox(
                title=self.title_text, model=self.model,
                version=self.version, session=self.session_id,
            )
        )

        pending: dict[str, ToolCallPart] = {}

        for msg in messages:
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
                    for t in texts:
                        await handle.write_answer(t.content)
                    await handle.finish()
                for p in msg.parts:
                    if isinstance(p, ToolCallPart):
                        pending[p.tool_call_id] = p

        for call in pending.values():
            await self.show_tool_call(call.tool_name, args=str(call.args))

        self._scroll.anchor()
