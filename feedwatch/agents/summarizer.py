import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feedwatch.config import settings
from feedwatch.models.article import Article

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def summarize_article(article: Article) -> str:
    text = f"Title: {article.title}\n"
    if article.description:
        text += f"Description: {article.description[:1000]}"

    client = _get_client()
    message = await client.messages.create(
        model=settings.claude_model,
        max_tokens=150,
        system="You are a news summarizer. Summarize the article in 1-2 sentences. Be factual and concise.",
        messages=[{"role": "user", "content": text}],
    )
    return message.content[0].text


async def summarize_pending(db: AsyncSession, batch_size: int = 20) -> int:
    if not settings.anthropic_api_key:
        return 0

    result = await db.execute(
        select(Article)
        .where(Article.summary == None)  # noqa: E711
        .where(Article.embedded == True)  # noqa: E712
        .limit(batch_size)
    )
    articles = result.scalars().all()

    for article in articles:
        try:
            article.summary = await summarize_article(article)
        except Exception:
            pass

    await db.commit()
    return len(articles)
