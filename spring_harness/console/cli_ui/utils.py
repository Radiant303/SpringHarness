import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable

# 节奏参数移植自 codex-rs/tui/src/streaming/chunking.rs 和 tui.rs
_TICK = 1 / 120  # 正常模式每 tick 给出一行（约 120fps，与 codex 的 commit tick 一致）

_ENTER_QUEUE_DEPTH = 8        # 积压 8 行进入追赶
_ENTER_OLDEST_AGE = 0.120     # 或最老的行等了 120ms
_EXIT_QUEUE_DEPTH = 2         # 回落到 2 行
_EXIT_OLDEST_AGE = 0.040      # 且最老行不超过 40ms
_EXIT_HOLD = 0.250            # 且持续 250ms，才退出追赶
_REENTER_HOLD = 0.250         # 退出后 250ms 内不轻易重新进入（防抖）
_SEVERE_QUEUE_DEPTH = 64      # 严重积压：64 行
_SEVERE_OLDEST_AGE = 0.300    # 或最老行 300ms，无视冷却立即追赶


class LinePacer:
    """攒 delta 成行，匀速逐行上屏；积压时自动批量追赶（codex TUI 同款节奏）。

    - 完整行进队列，半行留在源头 buffer 等换行；攒到 max_chars 仍无换行，
      整段进队列（无换行长文的硬兜底）；
    - 正常模式：每 _TICK 秒给出一行，制造逐行流淌的匀速感；
    - 追赶模式：队列 >= 8 行或最老行等 >= 120ms 时，一次给出全部积压；
      回落到 <= 2 行且最老 <= 40ms、持续 250ms 才恢复逐行；
      >= 64 行或 >= 300ms 的严重积压无视冷却立即追赶；
    - write() 是同步热路径（只 append + 拆行 + 排程），渲染全部在 flush_fn；
      flush_fn 收到的 batch 是一到多行拼接的文本；
    - 流结束必须调 drain()，它会把残余的半行也清掉；
    - 任意时刻最多一个 pump 在执行，flush_fn 不会被并发调用。
    """

    def __init__(
        self,
        flush_fn: Callable[[str], Awaitable[None]],
        max_chars: int = 1000,
    ) -> None:
        self._flush_fn = flush_fn
        self._max_chars = max_chars
        self._src: list[str] = []  # 源头 buffer：没到换行的部分
        self._src_size = 0
        self._queue: deque[tuple[str, float]] = deque()  # (完整行, 入队时刻)
        self._task: asyncio.Task[None] | None = None
        self._catch_up = False
        self._exit_since: float | None = None  # 退出条件开始持续满足的时刻
        self._exited_at = 0.0                  # 上次退出追赶的时刻
        self._drained = False

    def write(self, chunk: str) -> None:
        """热路径：append 后把完整行挪进队列，保证 pump 在跑。"""
        self._src.append(chunk)
        self._src_size += len(chunk)
        text = "".join(self._src)
        cut = text.rfind("\n") + 1
        if cut == 0 and self._src_size >= self._max_chars:
            cut = len(text)  # 硬兜底：无换行长文整段进队列
        if cut:
            now = time.monotonic()
            for line in text[:cut].splitlines(keepends=True):
                self._queue.append((line, now))
            tail = text[cut:]
            self._src = [tail] if tail else []
            self._src_size = len(tail)
        if self._task is None and self._queue:
            self._task = asyncio.ensure_future(self._pump())

    def _update_mode(self, now: float) -> None:
        """追赶模式的滞回状态机：进入快、退出慢，避免在边界来回抖。"""
        depth = len(self._queue)
        oldest_age = now - self._queue[0][1] if self._queue else 0.0
        severe = depth >= _SEVERE_QUEUE_DEPTH or oldest_age >= _SEVERE_OLDEST_AGE
        if self._catch_up:
            if depth <= _EXIT_QUEUE_DEPTH and oldest_age <= _EXIT_OLDEST_AGE:
                self._exit_since = self._exit_since or now
                if now - self._exit_since >= _EXIT_HOLD:
                    self._catch_up = False
                    self._exit_since = None
                    self._exited_at = now
            else:
                self._exit_since = None
        elif severe or (
            (depth >= _ENTER_QUEUE_DEPTH or oldest_age >= _ENTER_OLDEST_AGE)
            and now - self._exited_at >= _REENTER_HOLD
        ):
            self._catch_up = True

    def _drain_plan(self) -> int:
        """本 tick 给出多少行：追赶模式清空队列，正常模式一行。"""
        return len(self._queue) if self._catch_up else 1

    async def _pump(self) -> None:
        next_emit = time.monotonic()  # 第一行立即给出
        try:
            while self._queue and not self._drained:
                self._update_mode(time.monotonic())
                n = self._drain_plan()
                batch = "".join(self._queue.popleft()[0] for _ in range(n))
                await self._flush_fn(batch)
                if self._catch_up:
                    continue  # 追赶模式不等节拍
                # 绝对时刻表而不是相对 sleep：Windows 的 asyncio.sleep 有
                # 15.6ms 粒度，忙循环里还可能提前返回；睡到点不到就接着睡，
                # 睡过头了也不追欠账（重置为现在 + 一个 tick）。
                next_emit = max(next_emit + _TICK, time.monotonic())
                while (remaining := next_emit - time.monotonic()) > 0:
                    await asyncio.sleep(remaining)
        finally:
            self._task = None
            if self._queue and not self._drained:
                # 只在被取消打断时才会走到这：为残余的行补一个 pump
                self._task = asyncio.ensure_future(self._pump())

    async def drain(self) -> None:
        """流尾清场：等 pump 自然收束（不打断进行中的 flush，cancel 会把
        flush_fn 截断在半截写入上），再把残余（含半行）一次给出。"""
        self._drained = True
        task = self._task
        if task is not None:
            await task
        tail = "".join(self._src)
        if tail:
            self._queue.append((tail, time.monotonic()))
            self._src = []
            self._src_size = 0
        if self._queue:
            batch = "".join(line for line, _ in self._queue)
            self._queue.clear()
            await self._flush_fn(batch)


def format_num(n) -> str:
    if n >= 1_000_000:
        return f"{n // 1_000_000}M"
    elif n >= 1_000:
        return f"{n // 1_000}k"
    return str(n)
