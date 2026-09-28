"""Cancel expensive non-streaming work when its HTTP caller disconnects."""

import asyncio
from collections.abc import Awaitable

from fastapi import HTTPException, Request


async def avec_connexion[T](request: Request, operation: Awaitable[T]) -> T:
    async def depart():
        # The JSON body has already been parsed by FastAPI. Await the next ASGI
        # event directly: is_disconnected() uses an AnyIO cancellation scope
        # which can absorb task cancellation and strand the watcher at cleanup.
        while (await request.receive())["type"] != "http.disconnect":
            await asyncio.sleep(0)

    travail = asyncio.ensure_future(operation)
    surveillance = asyncio.create_task(depart())
    try:
        termine, _ = await asyncio.wait(
            [travail, surveillance], return_when=asyncio.FIRST_COMPLETED
        )
        if travail in termine:
            return await travail
        raise HTTPException(499, "Request cancelled.")
    finally:
        for task in (travail, surveillance):
            if not task.done():
                task.cancel()
        await asyncio.gather(travail, surveillance, return_exceptions=True)
