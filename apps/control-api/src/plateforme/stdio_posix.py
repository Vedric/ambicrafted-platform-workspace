"""Cancellable POSIX pipes for the local MCP server's public AsyncFile interface.

The SDK keeps protocol framing. These adapters own fd 0/1 while active,
restoring their descriptors and blocking modes even when setup fails.
"""

from __future__ import annotations

import asyncio
import io
import os
import stat
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from anyio import AsyncFile

MAX_FRAME_BYTES = 1024 * 1024


class _EntreePipe(AsyncFile[str]):
    def __init__(self, wrapped: io.TextIOWrapper, reader: asyncio.StreamReader):
        super().__init__(wrapped)
        self.reader = reader

    async def readline(self) -> str:
        # AsyncFile iteration delegates here: never submit a blocking read to
        # an AnyIO worker thread that cannot be cancelled while stdin is open.
        return (await self.reader.readline()).decode("utf-8", errors="replace")


class _SortiePipe(AsyncFile[str]):
    async def write(self, data: str) -> int:
        remaining = memoryview(data.encode("utf-8"))
        descriptor = self.wrapped.fileno()
        loop = asyncio.get_running_loop()
        while remaining:
            try:
                written = os.write(descriptor, remaining)
            except BlockingIOError:
                ready: asyncio.Future[None] = loop.create_future()

                def notify(waiter: asyncio.Future[None] = ready) -> None:
                    if not waiter.done():
                        waiter.set_result(None)

                loop.add_writer(descriptor, notify)
                try:
                    await ready
                finally:
                    loop.remove_writer(descriptor)
            else:
                if written == 0:
                    raise BrokenPipeError("MCP output closed")
                remaining = remaining[written:]
        return len(data)

    async def flush(self) -> None:
        # write() waits for each byte to reach the OS pipe, without a thread or
        # a second userspace buffer. A cancelled frame is not retried.
        return None


@asynccontextmanager
async def entree_stdio() -> AsyncIterator[AsyncFile[str]]:
    original = os.dup(0)
    blocking = os.get_blocking(original)
    pipe = None
    text = None
    transport = None
    try:
        pipe = os.fdopen(os.dup(original), "rb", buffering=0)
        reader = asyncio.StreamReader(limit=MAX_FRAME_BYTES)
        protocol = asyncio.StreamReaderProtocol(reader)
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, pipe)
        # As with the SDK default claim, backend/handler accidental reads see
        # EOF rather than consuming private MCP protocol messages.
        with open(os.devnull, "rb", buffering=0) as empty:  # noqa: ASYNC230 - fixed null device.
            os.dup2(empty.fileno(), 0)
        text = io.TextIOWrapper(pipe, encoding="utf-8", errors="replace")
        yield _EntreePipe(text, reader)
    finally:
        if transport is not None:
            transport.close()
        os.dup2(original, 0)
        os.set_blocking(0, blocking)
        os.close(original)
        if text is not None:
            text.close()
        elif pipe is not None:
            pipe.close()


@asynccontextmanager
async def sortie_stdio() -> AsyncIterator[AsyncFile[str]]:
    original = os.dup(1)
    blocking = os.get_blocking(original)
    text = None
    try:
        mode = os.fstat(original).st_mode
        if not (stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode)):
            raise ValueError("MCP output requires a POSIX pipe or socket")
        text = io.TextIOWrapper(os.fdopen(os.dup(original), "wb", buffering=0), encoding="utf-8")
        os.set_blocking(original, False)
        # Keep accidental print()/child output away from the MCP wire, just as
        # the SDK's default stdout claim does. Logs remain disabled by main().
        os.dup2(2, 1)
        yield _SortiePipe(text)
    finally:
        os.dup2(original, 1)
        os.set_blocking(1, blocking)
        os.close(original)
        if text is not None:
            text.close()
