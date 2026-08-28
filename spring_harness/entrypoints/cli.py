import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from tqdm import tqdm


class ImportProgressBar:
    def __init__(self, total_steps: int):
        self.total_steps = total_steps
        self.current_step = 0
        self.stop_event = threading.Event()
        self.pbar = None
        self._orig_stdout = sys.stdout
        self.ready_event = threading.Event()  # 添加就绪事件

    def __enter__(self):
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')

        self.pbar = tqdm(
            total=100,
            desc="启动进度",
            bar_format="{l_bar}{bar:20} {percentage:3.0f}%",
            file=self._orig_stdout
        )

        self.ready_event.set()

        def smooth_runner():
            self.ready_event.wait()

            step_idx = 0
            chunk = 100 / self.total_steps
            while not self.stop_event.is_set():
                time.sleep(0.04)
                step_idx += 1
                base = self.current_step * chunk
                fake_delta = (1 - (0.92 ** step_idx)) * 0.98 * chunk
                calculated = base + fake_delta

                if self.pbar is not None:
                    self.pbar.n = calculated if calculated < 100 else 99
                    self.pbar.refresh()

        self.thread = threading.Thread(target=smooth_runner, daemon=True)
        self.thread.start()
        return self

    def next_stage(self):
        self.current_step += 1
        if self.pbar is not None:
            self.pbar.n = (self.current_step / self.total_steps) * 100
            self.pbar.refresh()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)

        if self.pbar is not None:
            self.pbar.n = 100
            self.pbar.refresh()
            self.pbar.close()

        if sys.stdout != self._orig_stdout:
            sys.stdout.close()
            sys.stdout = self._orig_stdout


with ImportProgressBar(total_steps=1):
    from concurrent.futures import ThreadPoolExecutor

    from pydantic_ai import (
        Agent,
        ModelMessage,
        ModelRequest,
        ModelResponse,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    from spring_harness.console.approval import run_with_approval
    from spring_harness.console.cli_sink import CliSink
    from spring_harness.console.cli_ui.app import CliApp
    from spring_harness.console.cli_ui.widgets import WelcomeBox
    from spring_harness.console.renderer import EventStreamRenderer, make_diff
    from spring_harness.core.agent.agent import create_agent
    from spring_harness.core.agent.deps import CodingAgentDeps
    from spring_harness.core.services.session_store import SessionStore, _session_title


class MyBot(CliApp):
    def __init__(self, *args, resume_last: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._busy = False
        self._message_history: list[ModelMessage] = []
        self._session_deps = CodingAgentDeps.create_default(Path.cwd())
        self._agent = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._executor_future = self._executor.submit(create_agent, Path.cwd())

        sessions = SessionStore.list_sessions(Path.cwd())
        if resume_last and sessions:
            self._store, _ = sessions[-1]
            self._message_history = self._store.load_messages()
        else:
            self._store = SessionStore.create(Path.cwd())

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
            # 编辑类工具把改动 diff 带进审批弹窗，比截断的 JSON 参数更有决策价值
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
            # 失败时 result 不存在，all_messages() 无从谈起；钩子里存的消息快照
            # 是抢救上下文的唯一通道，不用它这一轮（用户问题+模型的全部尝试）就蒸发了
            if self._session_deps.last_messages:
                self._message_history = self._session_deps.last_messages
            raise
        finally:
            self._busy = False

        self._store.append(result.new_messages())
        self._message_history = result.all_messages()

    async def handle_command(self, command: str) -> None:
        if self._busy:
            await self.show_system("运行中，不能切换 session")
            return

        name, _, arg = command.partition(" ")
        arg = arg.strip()

        if name == "new":
            self._store = SessionStore.create(Path.cwd())
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
                lines = [
                    f"{i}. {meta['created_at'][:10]}  {_session_title(store)}"
                    for i, (store, meta) in enumerate(sessions, 1)
                ]
                await self.show_system("用 /resume <编号> 切换：\n" + "\n".join(lines))
                return
            try:
                self._store, _ = sessions[int(arg) - 1]
            except (ValueError, IndexError):
                await self.show_system(f"无效编号：{arg}")
                return
            self._message_history = self._store.load_messages()
            await self._rebuild_chat(self._message_history)
            await self.show_system(f"已切换到会话 {arg}")
            return

        await super().handle_command(command)

    async def _rebuild_chat(self, messages: list[ModelMessage]) -> None:
        """切换/恢复会话后重建聊天区：清空 + 把 history 逐条映射回组件。"""
        await self._scroll.remove_children()
        # remove_children 连 WelcomeBox 一起清了，补挂回来
        await self._scroll.mount(
            WelcomeBox(title=self.title_text, model=self.model, version=self.version)
        )

        # ToolCallPart 在 ModelResponse 里，结果 ToolReturnPart 在后面那条
        # ModelRequest 里，靠 tool_call_id 配对；见到 return 再一起渲染
        pending: dict[str, ToolCallPart] = {}

        for msg in messages:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                        await self.show_user(part.content)
                    elif isinstance(part, ToolReturnPart):
                        call = pending.pop(part.tool_call_id, None)
                        if call is not None:
                            await self.show_tool_call(
                                call.tool_name,
                                args=str(call.args),
                                result=str(part.content)[:500],  # 展示层截断，数据完整
                            )
            elif isinstance(msg, ModelResponse):
                # 一条回复可能有多个 TextPart，合并进同一条 assistant 消息
                texts = [p for p in msg.parts if isinstance(p, TextPart)]
                if texts:
                    handle = await self.start_assistant()
                    for t in texts:
                        await handle.write_answer(t.content)
                    await handle.finish()
                for p in msg.parts:
                    if isinstance(p, ToolCallPart):
                        pending[p.tool_call_id] = p
            # SystemPromptPart / ThinkingPart 跳过：前者不是给用户看的，
            # 后者的耗时统计是运行时数据，历史里回放不出来

        # 没等到结果的调用（上次会话在工具执行中被杀）：展示为无结果，还原现场
        for call in pending.values():
            await self.show_tool_call(call.tool_name, args=str(call.args))

        self._scroll.anchor()


def main() -> None:
    resume = "--continue" in sys.argv or "-c" in sys.argv
    MyBot(
        title="Spring Harness", model="K100-99M", version="0.1.0",
        resume_last=resume,
        commands=[("new", "New session"), ("resume", "Resume a session")],
    ).run(mouse=True)


if __name__ == "__main__":
    main()

# MyBot(title="Spring Harness", model="K3-256k", version="0.1.0").run(mouse=False)
# 禁用鼠标才能实现复制 或者shift来复制 但是失去滚动功能
