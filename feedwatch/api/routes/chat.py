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


_SIMPLE_PATTERNS = {
    "positive": ("positive", "nejlepší", "best", "good", "happy"),
    "negative": ("negative", "nejhorší", "worst", "bad", "sad", "crisis"),
    "recent":   ("recent", "latest", "new", "today", "dnes", "nové", "nejnovější"),
    "search":   (),
}

async def _no_key_response(message: str, db: AsyncSession):
    """Odpověď bez API klíče — jednoduché dotazy přímo z DB."""
    from sqlalchemy import select
    from feedwatch.models.article import Article
    from feedwatch.models.feed import Feed
    import re

    msg = message.lower()

    # positive / negative news
    for sentiment in ("positive", "negative"):
        keywords = {"positive": ("positive","nejlepší","pozitivní","good","happy","best"),
                    "negative": ("negative","nejhorší","negativní","bad","worst","sad")}
        if any(k in msg for k in keywords[sentiment]):
            result = await db.execute(
                select(Article)
                .where(Article.sentiment_label == sentiment)
                .order_by(Article.sentiment_score.desc() if sentiment == "positive"
                          else Article.sentiment_score.asc())
                .limit(8)
            )
            articles = result.scalars().all()
            if not articles:
                yield _sse("delta", {"text": f"Žádné {sentiment} články v databázi. Spusť refresh."})
            else:
                label = "🟢 Nejpozitivnější" if sentiment == "positive" else "🔴 Nejnegativnější"
                yield _sse("delta", {"text": f"**{label} články:**\n\n"})
                for a in articles:
                    score = f"{a.sentiment_score:+.2f}" if a.sentiment_score else ""
                    yield _sse("delta", {"text": f"**{score}** [{a.title}]({a.url})\n"})
            yield _sse("done", {})
            return

    # recent / latest
    if any(k in msg for k in ("recent","latest","new","today","dnes","nové","nejnovější","poslední")):
        from datetime import datetime, UTC, timedelta
        since = datetime.now(UTC) - timedelta(hours=24)
        result = await db.execute(
            select(Article).where(Article.fetched_at >= since)
            .order_by(Article.fetched_at.desc()).limit(10)
        )
        articles = result.scalars().all()
        yield _sse("delta", {"text": f"**Nejnovější články (posledních 24h):**\n\n"})
        for a in articles:
            emoji = "🟢" if a.sentiment_label == "positive" else "🔴" if a.sentiment_label == "negative" else "⚪"
            yield _sse("delta", {"text": f"{emoji} [{a.title}]({a.url})\n"})
        yield _sse("done", {})
        return

    # stats
    if any(k in msg for k in ("stats","statistik","how many","kolik","feeds","feedy")):
        from sqlalchemy import func
        total = (await db.execute(select(func.count(Article.id)))).scalar()
        feeds_count = (await db.execute(select(func.count(Feed.id)))).scalar()
        pos = (await db.execute(select(func.count(Article.id)).where(Article.sentiment_label=="positive"))).scalar()
        neg = (await db.execute(select(func.count(Article.id)).where(Article.sentiment_label=="negative"))).scalar()
        yield _sse("delta", {"text":
            f"**Statistiky feedwatch:**\n\n"
            f"📡 Feedů: **{feeds_count}**\n"
            f"📰 Článků celkem: **{total}**\n"
            f"🟢 Pozitivní: **{pos}**\n"
            f"🔴 Negativní: **{neg}**\n"
            f"⚪ Neutrální: **{total-pos-neg}**\n"
        })
        yield _sse("done", {})
        return

    # fallback — no key info + what works
    yield _sse("delta", {"text":
        "**Chat AI** potřebuje Anthropic API klíč pro složitější dotazy.\n\n"
        "**Bez klíče funguje:**\n"
        "- *\"Show positive news\"* — nejpozitivnější články\n"
        "- *\"Show negative news\"* — nejnegativnější články\n"
        "- *\"Latest news\"* nebo *\"Dnes\"* — nejnovější články\n"
        "- *\"Stats\"* nebo *\"Statistiky\"* — přehled databáze\n\n"
        "Pro plný AI chat spusť server s klíčem:\n"
        "```\nfeedwatch serve --api-key sk-ant-...\n```"
    })
    yield _sse("done", {})


async def _build_context(message: str, db: AsyncSession) -> str:
    """Předvyplní kontext z feedwatch DB a vloží ho do promptu."""
    from datetime import datetime, UTC, timedelta
    from sqlalchemy import select, func
    from feedwatch.models.article import Article
    from feedwatch.models.feed import Feed
    from feedwatch.services.embedder import semantic_search

    lines = ["=== FEEDWATCH DATABASE CONTEXT ===\n"]

    # stats
    total = (await db.execute(select(func.count(Article.id)))).scalar()
    feeds_count = (await db.execute(select(func.count(Feed.id)))).scalar()
    lines.append(f"Database: {total} articles from {feeds_count} feeds.\n")

    # semantic search based on message
    try:
        results = semantic_search(message, n_results=6)
        if results:
            lines.append("\nMost relevant articles for this query:")
            for r in results:
                m = r["metadata"]
                lines.append(f"- [{m['sentiment_label']}] {m['title']} | {m['url']}")
    except Exception:
        pass

    # recent articles
    since = datetime.now(UTC) - timedelta(hours=24)
    result = await db.execute(
        select(Article).where(Article.fetched_at >= since)
        .order_by(Article.fetched_at.desc()).limit(8)
    )
    recent = result.scalars().all()
    if recent:
        lines.append("\nRecent articles (last 24h):")
        for a in recent:
            lines.append(f"- [{a.sentiment_label}] {a.title} | {a.url}")

    lines.append("\n=== END CONTEXT ===\n")
    return "\n".join(lines)


async def _stream_via_claude_cli(message: str, history: list[dict], db: AsyncSession):
    """Stream přes claude CLI subprocess — používá subscription, nepotřebuje API klíč."""
    import asyncio
    import json as _json
    import shutil

    claude_bin = shutil.which("claude")
    if not claude_bin:
        yield _sse("delta", {"text": "claude CLI not found in PATH."})
        yield _sse("done", {})
        return

    # build context from DB
    yield _sse("tool_start", {"name": "fetching_context", "id": "ctx"})
    context = await _build_context(message, db)
    yield _sse("tool_result", {"name": "fetching_context", "result": "done"})

    # build full prompt
    parts = [
        "You are a news research assistant. Use the provided feedwatch database context to answer the question.\n",
        context,
    ]
    for msg in history[-6:]:
        role = "User" if msg["role"] == "user" else "Assistant"
        parts.append(f"{role}: {msg['content']}")
    parts.append(f"User: {message}")
    parts.append("\nAnswer based on the context above. Cite article titles and URLs.")
    full_prompt = "\n".join(parts)

    proc = await asyncio.create_subprocess_exec(
        claude_bin, "--print", "--output-format", "stream-json", "--verbose",
        "--no-session-persistence",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    proc.stdin.write(full_prompt.encode())
    await proc.stdin.drain()
    proc.stdin.close()

    buffer = b""
    while True:
        chunk = await proc.stdout.read(512)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                obj = _json.loads(line)
                if obj.get("type") == "assistant":
                    for block in obj.get("message", {}).get("content", []):
                        if block.get("type") == "text" and block.get("text"):
                            yield _sse("delta", {"text": block["text"]})
            except Exception:
                pass

    await proc.wait()
    yield _sse("done", {})


async def _stream_chat(message: str, history: list[dict], db: AsyncSession):
    if not settings.anthropic_api_key:
        from feedwatch.services.claude_session import chat as claude_chat, has_claude

        if has_claude():
            # fetch DB context
            yield _sse("tool_start", {"name": "fetching_context", "id": "ctx"})
            context = await _build_context(message, db)
            yield _sse("tool_result", {"name": "fetching_context", "result": "done"})

            # stream via persistent claude session
            async for text in claude_chat(message, context=context):
                yield _sse("delta", {"text": text})
            yield _sse("done", {})
            return

        # fallback: simple DB queries
        async for chunk in _no_key_response(message, db):
            yield chunk
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


@router.get("/status")
async def chat_status():
    """Stav claude session — je připravená?"""
    from feedwatch.services.claude_session import session_ready, has_claude
    return {
        "has_claude": has_claude(),
        "session_ready": session_ready(),
        "mode": "claude_cli" if has_claude() else "db_only",
    }


@router.post("/reset")
async def chat_reset():
    """Reset claude session — starts fresh conversation."""
    from feedwatch.services.claude_session import reset_session
    reset_session()
    return {"status": "reset"}


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
