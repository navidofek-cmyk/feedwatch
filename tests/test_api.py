import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock

from feedwatch.api.main import app
from feedwatch.db.database import Base, engine


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_add_and_list_feed():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/feeds/", json={
            "url": "http://example.com/rss",
            "name": "Example",
            "category": "tech",
        })
        assert resp.status_code == 201
        feed = resp.json()
        assert feed["name"] == "Example"

        resp = await client.get("/feeds/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_duplicate_feed_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {"url": "http://example.com/rss", "name": "X", "category": "tech"}
        await client.post("/feeds/", json=payload)
        resp = await client.post("/feeds/", json=payload)
        assert resp.status_code == 409


@pytest.mark.asyncio
async def test_ask_without_api_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/ask", json={"question": "What happened today?"})
    assert resp.status_code == 200
    assert "ANTHROPIC_API_KEY" in resp.json()["answer"]
