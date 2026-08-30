import asyncio
from collections.abc import Awaitable, Callable


class DeltaCoalescer:
    """把高频小 delta 攒成完整行的大批次，双触发：

    - 行制：buffer 里有完整行才 flush，且每次只取到最后一个换行符为止，
      半行留在 buffer 里等下次；
    - 字数制：攒到 max_chars 仍无换行，整段给出（无换行长文的硬兜底）。

    write() 是同步热路径（只 append + 排程），渲染全部发生在 flush_fn 里；
    流结束必须调 drain()，它会把残余的半行也清掉。
    任意时刻最多一个 flush 链在执行，flush_fn 不会被并发调用。
    """

    def __init__(
        self,
        flush_fn: Callable[[str], Awaitable[None]],
        max_chars: int = 1000,
    ) -> None:
        self._flush_fn = flush_fn
        self._max_chars = max_chars
        self._buf: list[str] = []
        self._size = 0
        self._task: asyncio.Task[None] | None = None

    def write(self, chunk: str) -> None:
        """热路径：O(1) append；有换行或字数到顶才排程 flush。"""
        self._buf.append(chunk)
        self._size += len(chunk)
        if self._task is None and ("\n" in chunk or self._size >= self._max_chars):
            self._task = asyncio.ensure_future(self._flush_once())

    def _take(self, force: bool = False) -> str:
        """取出本批上屏的文本：取到最后一个换行为止；无换行到顶才全取；
        force 清空一切（drain 用）。取不出东西返回空串。"""
        text = "".join(self._buf)
        if force:
            cut = len(text)
        else:
            cut = text.rfind("\n") + 1
            if cut == 0:
                if self._size < self._max_chars:
                    return ""
                cut = len(text)
        tail = text[cut:]
        self._buf = [tail] if tail else []
        self._size = len(tail)
        return text[:cut]

    def _takeable(self) -> bool:
        """不动 buffer 的判断：有完整行，或字数到顶。"""
        return self._size >= self._max_chars or any("\n" in part for part in self._buf)

    async def _flush_once(self) -> None:
        try:
            # while 而不是 if：flush 的 await 间隙里 write 只能 append
            # （_task 非 None，排不了新 flush），攒出的完整行由本循环接着吃掉，
            # 保证 flush_fn 不会被并发调用。半行取不出东西时循环自然退出。
            while text := self._take():
                await self._flush_fn(text)
        finally:
            self._task = None
            if self._takeable():
                # 只在被取消打断时才会走到这：为残余的完整行补一个排程
                self._task = asyncio.ensure_future(self._flush_once())

    async def drain(self) -> None:
        """流尾收尾：等掉已排程的 flush，再强制清掉残余的半行。"""
        task = self._task
        if task is not None:
            await task
        while text := self._take(force=True):
            await self._flush_fn(text)


def format_num(n) -> str:
    if n >= 1_000_000:
        return f"{n // 1_000_000}M"
    elif n >= 1_000:
        return f"{n // 1_000}k"
    return str(n)
