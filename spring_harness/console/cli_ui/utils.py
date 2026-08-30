import asyncio
from collections.abc import Awaitable, Callable


class DeltaCoalescer:
    """把高频小 delta 攒成低频大批次：最多每 interval 秒调一次 flush_fn。

    write() 是同步热路径（只 append + 排程），渲染全部发生在 flush_fn 里；
    流结束必须调 drain()，否则尾部 buffer 会丢。
    """

    def __init__(
        self,
        flush_fn: Callable[[str], Awaitable[None]],
        interval: float = 1 / 30,
    ) -> None:
        self._flush_fn = flush_fn
        self._interval = interval
        self._buf: list[str] = []
        self._task: asyncio.Task[None] | None = None

    def write(self, chunk: str) -> None:
        """热路径：O(1) append，然后确保恰好一个 flush 在排队。"""
        self._buf.append(chunk)
        if self._task is None:
            self._task = asyncio.ensure_future(self._run())

    async def _run(self) -> None:
        await asyncio.sleep(self._interval)
        try:
            await self._flush_once()
        finally:
            self._task = None

    async def _flush_once(self) -> None:
        if not self._buf:
            return
        text = "".join(self._buf)
        self._buf.clear()
        await self._flush_fn(text)

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
