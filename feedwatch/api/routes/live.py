"""
SSE live feed — push notifikace do prohlížeče.
Server-Sent Events endpoint který drží spojení otevřené
a posílá eventy při nových článcích, refreshi, atd.
"""
import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["live"])

# globální fronta eventů — CLI/refresh sem zapisuje, SSE čte
_subscribers: list[asyncio.Queue] = []


def broadcast(event: str, data: dict) -> None:
    """Pošli event všem připojeným klientům."""
    msg = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    dead = []
    for q in _subscribers:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.remove(q)


async def _stream(queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    # keep-alive ping každých 15s
    yield "event: connected\ndata: {}\n\n"
    while True:
        try:
            msg = await asyncio.wait_for(queue.get(), timeout=15)
            yield msg
        except asyncio.TimeoutError:
            yield ": ping\n\n"
        except Exception:
            break


@router.get("/live")
async def live_feed():
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.append(queue)

    async def cleanup():
        if queue in _subscribers:
            _subscribers.remove(queue)

    async def generator():
        try:
            async for chunk in _stream(queue):
                yield chunk
        finally:
            await cleanup()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
