from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feedwatch.models.article import Article

_analyzer = SentimentIntensityAnalyzer()


def score_text(text: str) -> tuple[float, str]:
    scores = _analyzer.polarity_scores(text)
    compound = scores["compound"]
    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"
    return compound, label


async def analyze_pending(db: AsyncSession) -> int:
    result = await db.execute(
        select(Article).where(Article.sentiment_score == None)  # noqa: E711
    )
    articles = result.scalars().all()

    for article in articles:
        text = article.title
        if article.description:
            text += " " + article.description[:300]
        score, label = score_text(text)
        article.sentiment_score = score
        article.sentiment_label = label

    await db.commit()
    return len(articles)
