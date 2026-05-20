import asyncio
from datetime import datetime, UTC
from email.utils import parsedate_to_datetime

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feedwatch.config import settings
from feedwatch.models.article import Article
from feedwatch.models.feed import Feed


def _parse_date(entry: feedparser.FeedParserDict) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        val = getattr(entry, field, None)
        if val:
            try:
                import time
                return datetime.fromtimestamp(time.mktime(val), tz=UTC)
            except Exception:
                pass
    for field in ("published", "updated"):
        val = entry.get(field, "")
        if val:
            try:
                return parsedate_to_datetime(val)
            except Exception:
                pass
    return None


def _entry_guid(entry: feedparser.FeedParserDict, feed_url: str) -> str:
    return entry.get("id") or entry.get("link") or f"{feed_url}#{entry.get('title', '')}"


async def _fetch_feed_raw(url: str, client: httpx.AsyncClient) -> feedparser.FeedParserDict | None:
    try:
        resp = await client.get(url, timeout=settings.fetch_timeout)
        resp.raise_for_status()
        return feedparser.parse(resp.text)
    except Exception:
        return None


async def fetch_one(feed: Feed, db: AsyncSession) -> int:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        parsed = await _fetch_feed_raw(feed.url, client)

    if not parsed or not parsed.entries:
        return 0

    existing_guids: set[str] = set(
        row[0]
        for row in (
            await db.execute(
                select(Article.guid).where(Article.feed_id == feed.id)
            )
        ).all()
    )

    new_articles: list[Article] = []
    for entry in parsed.entries:
        guid = _entry_guid(entry, feed.url)
        if guid in existing_guids:
            continue

        description = entry.get("summary") or entry.get("description") or ""
        if len(description) > 2000:
            description = description[:2000]

        article = Article(
            feed_id=feed.id,
            guid=guid,
            title=(entry.get("title") or "")[:1000],
            description=description or None,
            url=entry.get("link") or feed.url,
            author=entry.get("author", None),
            published_at=_parse_date(entry),
        )
        new_articles.append(article)

    if new_articles:
        db.add_all(new_articles)

    feed.last_fetched = datetime.now(UTC)
    await db.commit()
    return len(new_articles)


async def fetch_all(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(select(Feed).where(Feed.active == True))  # noqa: E712
    feeds = result.scalars().all()

    tasks = [fetch_one(feed, db) for feed in feeds]
    counts = await asyncio.gather(*tasks, return_exceptions=True)

    return {
        feed.name: (count if isinstance(count, int) else 0)
        for feed, count in zip(feeds, counts)
    }
