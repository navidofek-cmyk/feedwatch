import pytest
from unittest.mock import AsyncMock, patch
from feedwatch.models.feed import Feed
from feedwatch.services.fetcher import fetch_one


SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Article One</title>
      <link>http://example.com/1</link>
      <guid>http://example.com/1</guid>
      <description>First article description.</description>
    </item>
    <item>
      <title>Article Two</title>
      <link>http://example.com/2</link>
      <guid>http://example.com/2</guid>
    </item>
  </channel>
</rss>"""


@pytest.mark.asyncio
async def test_fetch_one_new_articles(db):
    feed = Feed(url="http://example.com/rss", name="Test", category="test")
    db.add(feed)
    await db.commit()

    mock_response = AsyncMock()
    mock_response.text = SAMPLE_RSS
    mock_response.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        count = await fetch_one(feed, db)

    assert count == 2


@pytest.mark.asyncio
async def test_fetch_one_deduplication(db):
    feed = Feed(url="http://example.com/rss", name="Test", category="test")
    db.add(feed)
    await db.commit()

    mock_response = AsyncMock()
    mock_response.text = SAMPLE_RSS
    mock_response.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        first = await fetch_one(feed, db)
        second = await fetch_one(feed, db)

    assert first == 2
    assert second == 0
