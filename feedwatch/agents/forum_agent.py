"""
Forum digest agent — shrne diskuze rodičů z fór a Redditu.
Najde vzory, opakující se témata, praktické rady z komunity.
"""
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
        "name": "search_forum_posts",
        "description": "Semantic search across forum posts and discussions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "n_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_forum_posts",
        "description": "Get recent posts from parent forums and Reddit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["forum/parents", "forum/reddit", "all"],
                    "default": "all",
                },
                "limit": {"type": "integer", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "get_top_discussed_topics",
        "description": "Find the most common/recurring topics in forum discussions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 30},
            },
            "required": [],
        },
    },
]

SYSTEM_PROMPT = """You are a specialist analyst for autism/ASD parent communities.
You have access to forum posts and discussions from parents of autistic children.
Your job is to:
- Find recurring themes, questions, and challenges parents face
- Identify practical tips and strategies that parents share with each other
- Highlight discussions about communication methods (PECS, VOKS, AAC)
- Surface emotional support patterns and community wisdom
- Note any mentions of schools, therapists, or educational strategies

Always respond in the same language the user asks in.
Be empathetic — these are real parents sharing real experiences.
Cite specific posts with their URLs when possible."""


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def _run_tool(name: str, inputs: dict, db: AsyncSession) -> str:
    if name == "search_forum_posts":
        results = semantic_search(inputs["query"], n_results=inputs.get("n_results", 10))
        if not results:
            return "No posts found."
        lines = []
        for r in results:
            m = r["metadata"]
            lines.append(f"- [{m['title']}]({m['url']}) | sentiment: {m['sentiment_label']} | score: {r['score']:.2f}")
        return "\n".join(lines)

    if name == "get_forum_posts":
        category = inputs.get("category", "all")
        limit = inputs.get("limit", 20)

        q = (
            select(Article, Feed.name.label("feed_name"), Feed.category.label("feed_category"))
            .join(Feed, Article.feed_id == Feed.id)
            .order_by(Article.fetched_at.desc())
            .limit(limit)
        )
        if category != "all":
            q = q.where(Feed.category == category)

        result = await db.execute(q)
        rows = result.all()

        if not rows:
            return f"No posts found for category: {category}"

        lines = []
        for article, feed_name, feed_cat in rows:
            lines.append(
                f"[{feed_name}] {article.title}\n"
                f"  URL: {article.url}\n"
                f"  Sentiment: {article.sentiment_label} ({article.sentiment_score:+.2f})\n"
                f"  Summary: {article.summary or article.description[:100] if article.description else 'N/A'}"
            )
        return "\n\n".join(lines)

    if name == "get_top_discussed_topics":
        limit = inputs.get("limit", 30)
        result = await db.execute(
            select(Article.title, Article.url, Article.sentiment_score)
            .join(Feed, Article.feed_id == Feed.id)
            .where(Feed.category.in_(["forum/parents", "forum/reddit"]))
            .order_by(Article.fetched_at.desc())
            .limit(limit)
        )
        rows = result.all()
        if not rows:
            return "No forum posts in database yet. Run: feedwatch autism"
        lines = [f"- {title} ({score:+.2f}) — {url}" for title, url, score in rows]
        return "\n".join(lines)

    return f"Unknown tool: {name}"


async def digest(question: str, db: AsyncSession) -> str:
    """Ask the forum agent about parent discussions."""
    if not settings.anthropic_api_key:
        return "ANTHROPIC_API_KEY not set in .env"

    client = _get_client()
    messages = [{"role": "user", "content": question}]

    while True:
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            return "".join(b.text for b in response.content if hasattr(b, "text"))

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await _run_tool(block.name, block.input, db)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return "No response generated."
