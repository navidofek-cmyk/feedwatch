from __future__ import annotations

import chromadb
from sentence_transformers import SentenceTransformer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feedwatch.config import settings
from feedwatch.models.article import Article

_model: SentenceTransformer | None = None
_chroma: chromadb.Collection | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embed_model)
    return _model


def _get_collection() -> chromadb.Collection:
    global _chroma
    if _chroma is None:
        client = chromadb.PersistentClient(path=settings.chroma_path)
        _chroma = client.get_or_create_collection("articles")
    return _chroma


async def embed_pending(db: AsyncSession) -> int:
    result = await db.execute(
        select(Article).where(Article.embedded == False)  # noqa: E712
    )
    articles = result.scalars().all()
    if not articles:
        return 0

    model = _get_model()
    collection = _get_collection()

    texts = [a.text_for_embedding for a in articles]
    embeddings = model.encode(texts, show_progress_bar=False).tolist()

    collection.upsert(
        ids=[str(a.id) for a in articles],
        embeddings=embeddings,
        documents=texts,
        metadatas=[
            {
                "title": a.title,
                "url": a.url,
                "feed_id": a.feed_id,
                "sentiment_label": a.sentiment_label or "unknown",
                "published_at": str(a.published_at) if a.published_at else "",
            }
            for a in articles
        ],
    )

    for article in articles:
        article.embedded = True

    await db.commit()
    return len(articles)


def semantic_search(query: str, n_results: int = 10) -> list[dict]:
    model = _get_model()
    collection = _get_collection()

    query_embedding = model.encode([query]).tolist()
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    output = []
    for i, doc_id in enumerate(results["ids"][0]):
        output.append(
            {
                "id": doc_id,
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "score": 1 - results["distances"][0][i],
            }
        )
    return output
