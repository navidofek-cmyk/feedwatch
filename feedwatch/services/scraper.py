"""
Forum and discussion scraper for sources without RSS feeds.
Supports: Reddit (via RSS), generic forum scraping (BeautifulSoup).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, UTC
from typing import TypedDict

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from feedwatch.models.article import Article
from feedwatch.models.feed import Feed


class ScrapedPost(TypedDict):
    guid: str
    title: str
    description: str
    url: str
    author: str | None
    published_at: datetime | None


def _make_guid(url: str, title: str) -> str:
    return hashlib.sha256(f"{url}:{title}".encode()).hexdigest()[:32]


# ── REDDIT (přes RSS) ─────────────────────────────────────────────────────────

REDDIT_AUTISM_FEEDS = [
    {
        "name": "Reddit r/autism",
        "url": "https://www.reddit.com/r/autism.rss?limit=50",
        "category": "forum/reddit",
    },
    {
        "name": "Reddit r/aspergers",
        "url": "https://www.reddit.com/r/aspergers.rss?limit=50",
        "category": "forum/reddit",
    },
    {
        "name": "Reddit r/autisminwomen",
        "url": "https://www.reddit.com/r/autisminwomen.rss?limit=50",
        "category": "forum/reddit",
    },
    {
        "name": "Reddit r/autism — PECS AAC",
        "url": "https://www.reddit.com/r/autism/search.rss?q=PECS+AAC+VOKS+communication&sort=new&limit=25",
        "category": "forum/reddit",
    },
    {
        "name": "Reddit r/specialed",
        "url": "https://www.reddit.com/r/specialed.rss?limit=50",
        "category": "forum/reddit",
    },
    {
        "name": "Reddit r/autismparents",
        "url": "https://www.reddit.com/r/autismparents.rss?limit=50",
        "category": "forum/parents",
    },
]


# ── GENERIC HTML SCRAPER ──────────────────────────────────────────────────────

async def _scrape_forum_page(url: str, client: httpx.AsyncClient, selectors: dict) -> list[ScrapedPost]:
    """
    Generic HTML scraper. selectors dict:
      post: CSS selector for each post container
      title: selector for title (relative to post)
      link: selector for link href (relative to post)
      author: selector for author (relative to post, optional)
      date: selector for date (relative to post, optional)
      body: selector for post body/preview (relative to post, optional)
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 feedwatch/0.1 (research)"}
        resp = await client.get(url, timeout=20, headers=headers)
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    posts: list[ScrapedPost] = []

    for item in soup.select(selectors["post"])[:30]:
        try:
            title_el = item.select_one(selectors["title"])
            link_el = item.select_one(selectors.get("link", selectors["title"]))
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = link_el.get("href", "") if link_el else ""
            if href and not href.startswith("http"):
                from urllib.parse import urljoin
                href = urljoin(url, href)

            author_el = item.select_one(selectors["author"]) if selectors.get("author") else None
            body_el = item.select_one(selectors["body"]) if selectors.get("body") else None

            posts.append(ScrapedPost(
                guid=_make_guid(href or url, title),
                title=title[:500],
                description=body_el.get_text(strip=True)[:800] if body_el else "",
                url=href or url,
                author=author_el.get_text(strip=True)[:100] if author_el else None,
                published_at=None,
            ))
        except Exception:
            continue

    return posts


# ── KNOWN FORUM SCRAPERS ──────────────────────────────────────────────────────
# Selektory pro konkrétní fora rodičů

FORUM_SCRAPERS = [
    {
        "name": "Wrong Planet Forums",
        "url": "https://wrongplanet.net/forums/viewforum.php?f=3",
        "category": "forum/parents",
        "selectors": {
            "post": "li.row.bg1, li.row.bg2",
            "title": "a.topictitle",
            "link": "a.topictitle",
            "author": "dd.lastpost span",
        },
    },
    {
        "name": "Autism Forums — Parents",
        "url": "https://www.autismforums.com/forums/parents-caregivers.18/",
        "category": "forum/parents",
        "selectors": {
            "post": "div.structItem-title",
            "title": "a",
            "link": "a",
        },
    },
]


# ── MAIN SCRAPE FUNCTION ──────────────────────────────────────────────────────

async def scrape_forum(feed: Feed, db: AsyncSession) -> int:
    """Scrape a forum feed. Used for feeds with source_type='scrape'."""
    scraper_config = next(
        (s for s in FORUM_SCRAPERS if s["url"] == feed.url or s["name"] == feed.name),
        None,
    )
    if not scraper_config:
        return 0

    async with httpx.AsyncClient(follow_redirects=True) as client:
        posts = await _scrape_forum_page(
            scraper_config["url"], client, scraper_config["selectors"]
        )

    return await _save_posts(posts, feed, db)


async def _save_posts(posts: list[ScrapedPost], feed: Feed, db: AsyncSession) -> int:
    from sqlalchemy import select

    existing = set(
        row[0] for row in (
            await db.execute(select(Article.guid).where(Article.feed_id == feed.id))
        ).all()
    )

    new_articles = []
    for post in posts:
        if post["guid"] in existing:
            continue
        article = Article(
            feed_id=feed.id,
            guid=post["guid"],
            title=post["title"],
            description=post["description"] or None,
            url=post["url"],
            author=post["author"],
            published_at=post["published_at"],
        )
        new_articles.append(article)

    if new_articles:
        db.add_all(new_articles)

    feed.last_fetched = datetime.now(UTC)
    await db.commit()
    return len(new_articles)


async def add_autism_feeds(db: AsyncSession) -> int:
    """Add all preset autism/PAS community feeds."""
    from sqlalchemy import select
    from feedwatch.models.feed import Feed

    added = 0
    for f in REDDIT_AUTISM_FEEDS:
        existing = (await db.execute(select(Feed).where(Feed.url == f["url"]))).scalar_one_or_none()
        if not existing:
            feed = Feed(url=f["url"], name=f["name"], category=f["category"])
            db.add(feed)
            added += 1

    await db.commit()
    return added
