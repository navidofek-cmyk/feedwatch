"""
Streaming chat endpoint — SSE stream z Claude API s tool use.
"""
import json
import asyncio
from datetime import datetime, UTC, timedelta

import anthropic
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from feedwatch.config import settings
from feedwatch.db import get_db
from feedwatch.models.article import Article
from feedwatch.models.feed import Feed
from feedwatch.services.embedder import semantic_search

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


TOOLS = [
    {
        "name": "semantic_search",
        "description": "Search articles using semantic similarity. Use for topic-based queries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "n_results": {"type": "integer", "default": 8},
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
                "hours": {"type": "integer", "default": 24},
                "limit": {"type": "integer", "default": 10},
                "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral", "all"], "default": "all"},
            },
            "required": [],
        },
    },
    {
        "name": "get_feed_stats",
        "description": "Get statistics about feeds and sentiment distribution.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_forum_posts",
        "description": "Get recent posts from parent forums and Reddit autism communities.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 15}},
            "required": [],
        },
    },
]

SYSTEM = """You are a helpful news and community research assistant with access to a personal RSS feed database and autism/PAS parent forum posts.

You can search articles semantically, get recent news, check sentiment trends, and read what parents are discussing in autism communities.

When answering:
- Always cite sources with URLs
- Mention sentiment when relevant (positive/negative news)
- Be concise but thorough
- If asked about autism, VOKS, PECS, AAC — focus on practical community insights
- Respond in the same language the user writes in"""


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _run_tool(name: str, inputs: dict, db: AsyncSession) -> str:
    if name == "semantic_search":
        results = semantic_search(inputs.get("query", ""), inputs.get("n_results", 8))
        if not results:
            return "No results found."
        return "\n".join(
            f"- **{r['metadata']['title']}** | {r['metadata']['url']} | sentiment: {r['metadata']['sentiment_label']} | score: {r['score']:.2f}"
            for r in results
        )

    if name == "get_recent_articles":
        hours = inputs.get("hours", 24)
        limit = inputs.get("limit", 10)
        sentiment = inputs.get("sentiment", "all")
        since = datetime.now(UTC) - timedelta(hours=hours)
        q = select(Article).where(Article.fetched_at >= since).order_by(Article.fetched_at.desc()).limit(limit)
        if sentiment != "all":
            q = q.where(Article.sentiment_label == sentiment)
        result = await db.execute(q)
        articles = result.scalars().all()
        if not articles:
            return f"No articles in the last {hours}h."
        return "\n".join(
            f"- **{a.title}** | {a.url} | {a.sentiment_label} ({a.sentiment_score:+.2f})"
            for a in articles
        )

    if name == "get_feed_stats":
        feeds_result = await db.execute(
            select(Feed.name, func.count(Article.id))
            .outerjoin(Article)
            .group_by(Feed.id)
        )
        sentiment_result = await db.execute(
            select(Article.sentiment_label, func.count(Article.id)).group_by(Article.sentiment_label)
        )
        feeds = feeds_result.all()
        sentiments = {lbl or "unknown": cnt for lbl, cnt in sentiment_result.all()}
        lines = ["**Feeds:**"] + [f"  {name}: {count} articles" for name, count in feeds]
        lines += ["**Sentiment:**"] + [f"  {k}: {v}" for k, v in sentiments.items()]
        return "\n".join(lines)

    if name == "get_forum_posts":
        limit = inputs.get("limit", 15)
        result = await db.execute(
            select(Article, Feed.name.label("fn"))
            .join(Feed)
            .where(Feed.category.in_(["forum/parents", "forum/reddit"]))
            .order_by(Article.fetched_at.desc())
            .limit(limit)
        )
        rows = result.all()
        if not rows:
            return "No forum posts. Run: feedwatch autism && feedwatch refresh"
        return "\n".join(
            f"- [{fn}] **{a.title}** | {a.url}"
            for a, fn in rows
        )

    return f"Unknown tool: {name}"


async def _stream_chat(message: str, history: list[dict], db: AsyncSession):
    if not settings.anthropic_api_key:
        yield _sse("error", {"text": "ANTHROPIC_API_KEY not set in .env"})
        return

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages = history + [{"role": "user", "content": message}]

    while True:
        # stream Claude response
        full_text = ""
        tool_uses = []
        stop_reason = None

        async with client.messages.stream(
            model=settings.claude_model,
            max_tokens=1024,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        ) as stream:
            async for event in stream:
                # text delta
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        full_text += event.delta.text
                        yield _sse("delta", {"text": event.delta.text})

                # tool use starting
                elif event.type == "content_block_start":
                    if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                        yield _sse("tool_start", {
                            "name": event.content_block.name,
                            "id": event.content_block.id,
                        })

                # message done
                elif event.type == "message_delta":
                    if hasattr(event.delta, "stop_reason"):
                        stop_reason = event.delta.stop_reason

            # get full message for tool use
            final_msg = await stream.get_final_message()

        if stop_reason == "end_turn" or not any(b.type == "tool_use" for b in final_msg.content):
            yield _sse("done", {})
            break

        # handle tool calls
        messages.append({"role": "assistant", "content": final_msg.content})
        tool_results = []

        for block in final_msg.content:
            if block.type == "tool_use":
                yield _sse("tool_run", {"name": block.name, "input": block.input})
                result = await _run_tool(block.name, block.input, db)
                yield _sse("tool_result", {"name": block.name, "result": result[:200]})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        messages.append({"role": "user", "content": tool_results})


@router.post("/stream")
async def chat_stream(payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    async def generator():
        async for chunk in _stream_chat(payload.message, payload.history, db):
            yield chunk

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
