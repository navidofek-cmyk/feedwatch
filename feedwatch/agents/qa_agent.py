import json
from datetime import datetime, UTC, timedelta

import anthropic
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from feedwatch.config import settings
from feedwatch.models.article import Article
from feedwatch.models.feed import Feed
from feedwatch.services.embedder import semantic_search

_client: anthropic.AsyncAnthropic | None = None

TOOLS = [
    {
        "name": "semantic_search",
        "description": "Search articles using semantic/vector similarity. Use for topic-based queries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "n_results": {"type": "integer", "default": 8, "description": "Number of results"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_recent_articles",
        "description": "Get the most recent articles from the last N hours.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "default": 24, "description": "How many hours back"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "get_feed_stats",
        "description": "Get statistics about all feeds: article counts, sentiment distribution.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_articles_by_sentiment",
        "description": "Get articles filtered by sentiment label.",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "enum": ["positive", "negative", "neutral"],
                    "description": "Sentiment label",
                },
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["label"],
        },
    },
]


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def _run_tool(name: str, inputs: dict, db: AsyncSession) -> str:
    if name == "semantic_search":
        results = semantic_search(inputs["query"], inputs.get("n_results", 8))
        if not results:
            return "No articles found."
        lines = []
        for r in results:
            meta = r["metadata"]
            lines.append(
                f"- [{meta['title']}]({meta['url']}) | sentiment: {meta['sentiment_label']} | score: {r['score']:.2f}"
            )
        return "\n".join(lines)

    if name == "get_recent_articles":
        hours = inputs.get("hours", 24)
        limit = inputs.get("limit", 10)
        since = datetime.now(UTC) - timedelta(hours=hours)
        result = await db.execute(
            select(Article)
            .where(Article.fetched_at >= since)
            .order_by(Article.fetched_at.desc())
            .limit(limit)
        )
        articles = result.scalars().all()
        if not articles:
            return f"No articles in the last {hours} hours."
        lines = [
            f"- {a.title} | {a.url} | sentiment: {a.sentiment_label}"
            for a in articles
        ]
        return "\n".join(lines)

    if name == "get_feed_stats":
        result = await db.execute(
            select(Feed.name, func.count(Article.id))
            .join(Article, Feed.id == Article.feed_id, isouter=True)
            .group_by(Feed.id)
        )
        rows = result.all()
        sentiment_result = await db.execute(
            select(Article.sentiment_label, func.count(Article.id))
            .group_by(Article.sentiment_label)
        )
        sentiment_rows = sentiment_result.all()

        stats = {
            "feeds": [{"name": name, "articles": count} for name, count in rows],
            "sentiment": {label or "unknown": count for label, count in sentiment_rows},
        }
        return json.dumps(stats, indent=2)

    if name == "get_articles_by_sentiment":
        label = inputs["label"]
        limit = inputs.get("limit", 10)
        result = await db.execute(
            select(Article)
            .where(Article.sentiment_label == label)
            .order_by(Article.fetched_at.desc())
            .limit(limit)
        )
        articles = result.scalars().all()
        if not articles:
            return f"No {label} articles found."
        lines = [f"- {a.title} | {a.url}" for a in articles]
        return "\n".join(lines)

    return f"Unknown tool: {name}"


async def ask(question: str, db: AsyncSession) -> str:
    if not settings.anthropic_api_key:
        return "ANTHROPIC_API_KEY not set. Add it to .env file."

    client = _get_client()
    messages = [{"role": "user", "content": question}]

    system = (
        "You are a news research assistant with access to a personal RSS feed database. "
        "Use the available tools to search and retrieve articles, then answer the user's question "
        "with specific references to articles. Always cite sources with URLs."
    )

    while True:
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            return "".join(
                block.text for block in response.content if hasattr(block, "text")
            )

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    result = await _run_tool(block.name, block.input, db)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return "No response generated."
