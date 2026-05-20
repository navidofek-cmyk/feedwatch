from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feedwatch.db import get_db
from feedwatch.models.article import Article
from feedwatch.api.schemas import ArticleOut

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("/", response_model=list[ArticleOut])
async def list_articles(
    feed_id: int | None = Query(None),
    sentiment: str | None = Query(None, pattern="^(positive|negative|neutral)$"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = select(Article).order_by(Article.fetched_at.desc()).limit(limit).offset(offset)
    if feed_id is not None:
        q = q.where(Article.feed_id == feed_id)
    if sentiment is not None:
        q = q.where(Article.sentiment_label == sentiment)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/search", response_model=list[ArticleOut])
async def search_articles(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db),
):
    from feedwatch.services.embedder import semantic_search
    from sqlalchemy import select

    results = semantic_search(q, n_results=limit)
    if not results:
        return []
    ids = [int(r["id"]) for r in results]
    result = await db.execute(select(Article).where(Article.id.in_(ids)))
    articles = {a.id: a for a in result.scalars().all()}
    return [articles[i] for i in ids if i in articles]


@router.get("/{article_id}", response_model=ArticleOut)
async def get_article(article_id: int, db: AsyncSession = Depends(get_db)):
    article = await db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")
    return article
