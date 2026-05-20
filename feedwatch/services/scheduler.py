from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from feedwatch.config import settings

_scheduler: AsyncIOScheduler | None = None


async def _refresh_job() -> None:
    from feedwatch.db import AsyncSessionLocal
    from feedwatch.services.fetcher import fetch_all
    from feedwatch.services.analyzer import analyze_pending
    from feedwatch.services.embedder import embed_pending
    from feedwatch.agents.summarizer import summarize_pending

    async with AsyncSessionLocal() as db:
        await fetch_all(db)
        await analyze_pending(db)
        await embed_pending(db)
        await summarize_pending(db)


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(
            _refresh_job,
            trigger=IntervalTrigger(minutes=settings.scheduler_interval_minutes),
            id="refresh",
            replace_existing=True,
        )
    return _scheduler
