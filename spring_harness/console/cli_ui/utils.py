import asyncio
from collections.abc import Awaitable, Callable


class DeltaCoalescer:
    """把高频小 delta 攒成低频大批次，双触发：

    - 时间制：最多每 interval 秒 flush 一次（延迟有上界）；
    - 字数制：buffer 攒到 max_chars 立即 flush（单帧工作量有上界）。

    write() 是同步热路径（只 append + 排程），渲染全部发生在 flush_fn 里；
    流结束必须调 drain()，否则尾部 buffer 会丢。
    任意时刻最多一个 flush 链在执行，flush_fn 不会被并发调用。
    """

    def __init__(
        self,
        flush_fn: Callable[[str], Awaitable[None]],
        interval: float = 1 / 30,
        max_chars: int = 200,
    ) -> None:
        self._flush_fn = flush_fn
        self._interval = interval
        self._max_chars = max_chars
        self._buf: list[str] = []
        self._size = 0
        self._task: asyncio.Task[None] | None = None

    def write(self, chunk: str) -> None:
        """热路径：O(1) append，然后确保恰好一个 flush 在排队。"""
        self._buf.append(chunk)
        self._size += len(chunk)
        if self._task is None:
            self._schedule()

    def _schedule(self) -> None:
        """按当前 buffer 大小决定：到阈值立即 flush，否则攒一个 interval。"""
        if self._size >= self._max_chars:
            self._task = asyncio.ensure_future(self._flush_once())
        else:
            self._task = asyncio.ensure_future(self._run())

    async def _run(self) -> None:
        await asyncio.sleep(self._interval)
        await self._flush_once()

    async def _flush_once(self) -> None:
        try:
            # while 而不是 if：flush 的 await 间隙里 write 只能 append
            # （_task 非 None，排不了新 flush），这些增量由本循环接着吃掉，
            # 保证 flush_fn 不会被并发调用。
            while self._buf:
                text = "".join(self._buf)
                self._buf.clear()
                self._size = 0
                await self._flush_fn(text)
        finally:
            self._task = None
            if self._buf:
                # 只在被取消打断时才会走到这：为残余 delta 补一个排程
                self._schedule()

    async def drain(self) -> None:
        """流尾收尾：等掉已排程的 flush（最多一个 interval），再清残余。"""
        task = self._task
        if task is not None:
            await task
        await self._flush_once()


def format_num(n) -> str:
    if n >= 1_000_000:
        return f"{n // 1_000_000}M"
    elif n >= 1_000:
        return f"{n // 1_000}k"
    return str(n)
