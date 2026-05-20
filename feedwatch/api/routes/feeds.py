from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feedwatch.db import get_db
from feedwatch.models.feed import Feed
from feedwatch.api.schemas import FeedCreate, FeedOut

router = APIRouter(prefix="/feeds", tags=["feeds"])


@router.get("/", response_model=list[FeedOut])
async def list_feeds(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Feed).order_by(Feed.name))
    return result.scalars().all()


@router.post("/", response_model=FeedOut, status_code=201)
async def add_feed(payload: FeedCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Feed).where(Feed.url == payload.url))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Feed with this URL already exists.")

    feed = Feed(url=payload.url, name=payload.name, category=payload.category)
    db.add(feed)
    await db.commit()
    await db.refresh(feed)
    return feed


@router.delete("/{feed_id}", status_code=204)
async def delete_feed(feed_id: int, db: AsyncSession = Depends(get_db)):
    feed = await db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found.")
    await db.delete(feed)
    await db.commit()


@router.patch("/{feed_id}/toggle", response_model=FeedOut)
async def toggle_feed(feed_id: int, db: AsyncSession = Depends(get_db)):
    feed = await db.get(Feed, feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found.")
    feed.active = not feed.active
    await db.commit()
    await db.refresh(feed)
    return feed
