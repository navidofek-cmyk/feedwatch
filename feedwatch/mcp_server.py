"""
feedwatch MCP Server
────────────────────
Exposuje feedwatch jako MCP nástroje pro Claude Code a jiné MCP klienty.

Konfigurace v Claude Code (~/.claude/settings.json):
{
  "mcpServers": {
    "feedwatch": {
      "command": "uv",
      "args": ["run", "feedwatch", "mcp"],
      "cwd": "/path/to/feedwatch"
    }
  }
}

Po přidání stačí v Claude Code napsat:
  "Co se dnes děje na Redditu o autismu?"
  "Najdi příspěvky o VOKS od rodičů"
  "Shrni dnešní novinky z mých feedů"
"""
import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
)

from feedwatch.db import init_db, AsyncSessionLocal

server = Server("feedwatch")


# ── HELPERS ───────────────────────────────────────────────────────────────────

async def _with_db(coro):
    await init_db()
    async with AsyncSessionLocal() as db:
        return await coro(db)


# ── TOOLS ─────────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="fw_search",
            description="Semantic vector search across all RSS articles and forum posts. Finds content by meaning, not just keywords.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "n": {"type": "integer", "default": 10, "description": "Number of results"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="fw_recent",
            description="Get the most recent articles from all feeds.",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours": {"type": "integer", "default": 24},
                    "limit": {"type": "integer", "default": 10},
                    "sentiment": {
                        "type": "string",
                        "enum": ["positive", "negative", "neutral", "all"],
                        "default": "all",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="fw_ask",
            description="Ask the feedwatch Q&A agent a question about your feeds. Uses Claude with tool use internally.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="fw_forums",
            description="Ask the forum digest agent about parent discussions on Reddit and autism forums.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "default": "What are parents of autistic children discussing most?",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="fw_feeds",
            description="List all configured RSS feeds and forum sources.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="fw_stats",
            description="Get statistics: total articles, sentiment breakdown, feeds count.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="fw_refresh",
            description="Trigger a full refresh: fetch new articles from all feeds, analyze sentiment, embed, summarize.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="fw_top",
            description="Show top positive and top negative articles from the last N hours.",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours": {"type": "integer", "default": 24},
                    "n": {"type": "integer", "default": 5},
                },
                "required": [],
            },
        ),
    ]


# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
    try:
        result = await _dispatch(name, arguments)
        return CallToolResult(content=[TextContent(type="text", text=result)])
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {e}")],
            isError=True,
        )


async def _dispatch(name: str, args: dict) -> str:
    # ── fw_search ──
    if name == "fw_search":
        from feedwatch.services.embedder import semantic_search
        results = semantic_search(args["query"], n_results=args.get("n", 10))
        if not results:
            return "No results found."
        lines = []
        for r in results:
            m = r["metadata"]
            lines.append(
                f"**{m['title']}**\n"
                f"URL: {m['url']}\n"
                f"Sentiment: {m['sentiment_label']} | Score: {r['score']:.2f}\n"
            )
        return "\n".join(lines)

    # ── fw_recent ──
    if name == "fw_recent":
        from datetime import datetime, UTC, timedelta
        from sqlalchemy import select
        from feedwatch.models.article import Article

        hours = args.get("hours", 24)
        limit = args.get("limit", 10)
        sentiment = args.get("sentiment", "all")
        since = datetime.now(UTC) - timedelta(hours=hours)

        async def _get(db):
            q = (
                select(Article)
                .where(Article.fetched_at >= since)
                .order_by(Article.fetched_at.desc())
                .limit(limit)
            )
            if sentiment != "all":
                q = q.where(Article.sentiment_label == sentiment)
            result = await db.execute(q)
            return result.scalars().all()

        articles = await _with_db(_get)
        if not articles:
            return f"No articles in the last {hours} hours."
        lines = []
        for a in articles:
            lines.append(
                f"**{a.title}**\n"
                f"URL: {a.url}\n"
                f"Sentiment: {a.sentiment_label} ({a.sentiment_score:+.2f})\n"
                f"Summary: {a.summary or '—'}\n"
            )
        return "\n".join(lines)

    # ── fw_ask ──
    if name == "fw_ask":
        from feedwatch.agents.qa_agent import ask
        return await _with_db(lambda db: ask(args["question"], db))

    # ── fw_forums ──
    if name == "fw_forums":
        from feedwatch.agents.forum_agent import digest
        question = args.get("question", "What are parents of autistic children discussing most?")
        return await _with_db(lambda db: digest(question, db))

    # ── fw_feeds ──
    if name == "fw_feeds":
        from sqlalchemy import select, func
        from feedwatch.models.feed import Feed
        from feedwatch.models.article import Article

        async def _get(db):
            result = await db.execute(
                select(Feed, func.count(Article.id))
                .outerjoin(Article)
                .group_by(Feed.id)
                .order_by(Feed.name)
            )
            return result.all()

        rows = await _with_db(_get)
        if not rows:
            return "No feeds configured. Run: feedwatch add <url> --name <name>"
        lines = [f"- **{feed.name}** ({feed.category}) — {count} articles — {'active' if feed.active else 'inactive'}"
                 for feed, count in rows]
        return "\n".join(lines)

    # ── fw_stats ──
    if name == "fw_stats":
        from sqlalchemy import select, func
        from feedwatch.models.article import Article
        from feedwatch.models.feed import Feed

        async def _get(db):
            total = (await db.execute(select(func.count(Article.id)))).scalar()
            sentiment = (await db.execute(
                select(Article.sentiment_label, func.count(Article.id)).group_by(Article.sentiment_label)
            )).all()
            feeds = (await db.execute(select(func.count(Feed.id)))).scalar()
            return total, sentiment, feeds

        total, sentiment, feeds = await _with_db(_get)
        s = {label or "unknown": count for label, count in sentiment}
        return (
            f"**feedwatch stats**\n"
            f"Feeds: {feeds}\n"
            f"Total articles: {total}\n"
            f"Positive: {s.get('positive', 0)}\n"
            f"Neutral: {s.get('neutral', 0)}\n"
            f"Negative: {s.get('negative', 0)}\n"
        )

    # ── fw_refresh ──
    if name == "fw_refresh":
        from feedwatch.services.fetcher import fetch_all
        from feedwatch.services.analyzer import analyze_pending
        from feedwatch.services.embedder import embed_pending
        from feedwatch.agents.summarizer import summarize_pending

        async def _refresh(db):
            fetched = await fetch_all(db)
            analyzed = await analyze_pending(db)
            embedded = await embed_pending(db)
            summarized = await summarize_pending(db)
            total = sum(fetched.values())
            return (
                f"Refresh complete:\n"
                f"New articles: {total}\n"
                f"Analyzed: {analyzed}\n"
                f"Embedded: {embedded}\n"
                f"Summarized: {summarized}\n"
                f"\nPer feed:\n" +
                "\n".join(f"  {name}: {count}" for name, count in fetched.items())
            )

        return await _with_db(_refresh)

    # ── fw_top ──
    if name == "fw_top":
        from datetime import datetime, UTC, timedelta
        from sqlalchemy import select
        from feedwatch.models.article import Article

        hours = args.get("hours", 24)
        n = args.get("n", 5)
        since = datetime.now(UTC) - timedelta(hours=hours)

        async def _get(db):
            result = await db.execute(
                select(Article)
                .where(Article.fetched_at >= since)
                .where(Article.sentiment_score.isnot(None))
                .order_by(Article.sentiment_score.desc())
                .limit(n * 3)
            )
            return result.scalars().all()

        articles = await _with_db(_get)
        positive = [a for a in articles if a.sentiment_label == "positive"][:n]
        negative = sorted(
            [a for a in articles if a.sentiment_label == "negative"],
            key=lambda x: x.sentiment_score,
        )[:n]

        def _fmt(items, label):
            if not items:
                return f"**{label}:** none\n"
            lines = [f"**{label}:**"]
            for a in items:
                lines.append(f"  {a.sentiment_score:+.2f} — {a.title}\n  {a.url}")
            return "\n".join(lines)

        return _fmt(positive, "Top positive") + "\n\n" + _fmt(negative, "Top negative")

    return f"Unknown tool: {name}"


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

async def run():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    asyncio.run(run())
