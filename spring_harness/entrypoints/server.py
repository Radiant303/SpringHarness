import asyncio
import sys
import threading

from spring_harness.core.log import logger
from spring_harness.core.rpc.connection import JsonRpcConnection
from spring_harness.core.rpc.server import AppServer


async def _amain() -> None:
    loop = asyncio.get_running_loop()
    inbox: asyncio.Queue[str | None] = asyncio.Queue()

    def reader() -> None:
        for line in sys.stdin.buffer:
            loop.call_soon_threadsafe(inbox.put_nowait, line.decode("utf-8", "replace"))
        loop.call_soon_threadsafe(inbox.put_nowait, None)  # EOF

    threading.Thread(target=reader, daemon=True).start()

    async def read_line() -> str | None:
        return await inbox.get()

    def write(line: str) -> None:
        sys.stdout.buffer.write(line.encode("utf-8") + b"\n")
        sys.stdout.buffer.flush()

    async def write_line(line: str) -> None:
        task = asyncio.create_task(asyncio.to_thread(write, line))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    connection = JsonRpcConnection(read_line, write_line)
    server = AppServer(connection)
    logger.info("app server 启动（stdio）")
    try:
        await connection.run(server.handle_request, server.handle_notification)
    finally:
        await server.shutdown()
        logger.info("app server 退出")


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
