from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from feedwatch.db import get_db
from feedwatch.services.fetcher import fetch_all
from feedwatch.services.analyzer import analyze_pending
from feedwatch.services.embedder import embed_pending
from feedwatch.agents.summarizer import summarize_pending
from feedwatch.agents.qa_agent import ask
from feedwatch.api.schemas import RefreshResult, AskRequest, AskResponse
from feedwatch.api.routes.live import broadcast

router = APIRouter(tags=["actions"])


@router.post("/refresh", response_model=RefreshResult)
async def refresh(db: AsyncSession = Depends(get_db)):
    broadcast("status", {"msg": "🔄 Fetching feeds..."})
    fetched = await fetch_all(db)

    broadcast("status", {"msg": "😊 Analyzing sentiment..."})
    analyzed = await analyze_pending(db)

    broadcast("status", {"msg": "🧠 Embedding articles..."})
    embedded = await embed_pending(db)

    broadcast("status", {"msg": "✍️ Summarizing..."})
    summarized = await summarize_pending(db)

    total = sum(fetched.values())
    broadcast("refresh_done", {
        "total": total,
        "analyzed": analyzed,
        "embedded": embedded,
        "summarized": summarized,
        "feeds": fetched,
    })
    return RefreshResult(
        fetched=fetched,
        analyzed=analyzed,
        embedded=embedded,
        summarized=summarized,
    )


@router.post("/ask", response_model=AskResponse)
async def ask_agent(payload: AskRequest, db: AsyncSession = Depends(get_db)):
    answer = await ask(payload.question, db)
    return AskResponse(answer=answer)
