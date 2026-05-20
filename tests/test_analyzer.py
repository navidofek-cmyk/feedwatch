import pytest
from feedwatch.services.analyzer import score_text, analyze_pending
from feedwatch.models.article import Article
from feedwatch.models.feed import Feed


@pytest.mark.asyncio
async def test_score_positive():
    score, label = score_text("Amazing breakthrough! Scientists celebrate huge success.")
    assert label == "positive"
    assert score > 0.05


@pytest.mark.asyncio
async def test_score_negative():
    score, label = score_text("Terrible disaster kills thousands, catastrophic failure.")
    assert label == "negative"
    assert score < -0.05


@pytest.mark.asyncio
async def test_score_neutral():
    score, label = score_text("The meeting is scheduled for Tuesday.")
    assert label == "neutral"


@pytest.mark.asyncio
async def test_analyze_pending(db):
    feed = Feed(url="http://example.com/rss", name="Test", category="test")
    db.add(feed)
    await db.flush()

    article = Article(
        feed_id=feed.id,
        guid="test-guid-1",
        title="Scientists make amazing discovery",
        url="http://example.com/article1",
    )
    db.add(article)
    await db.commit()

    count = await analyze_pending(db)
    assert count == 1
    assert article.sentiment_label in ("positive", "negative", "neutral")
    assert article.sentiment_score is not None
