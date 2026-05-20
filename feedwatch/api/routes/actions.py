from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from feedwatch.db import get_db
from feedwatch.services.fetcher import fetch_all
from feedwatch.services.analyzer import analyze_pending
from feedwatch.services.embedder import embed_pending
from feedwatch.agents.summarizer import summarize_pending
from feedwatch.agents.qa_agent import ask
from feedwatch.api.schemas import RefreshResult, AskRequest, AskResponse

router = APIRouter(tags=["actions"])


@router.post("/refresh", response_model=RefreshResult)
async def refresh(db: AsyncSession = Depends(get_db)):
    fetched = await fetch_all(db)
    analyzed = await analyze_pending(db)
    embedded = await embed_pending(db)
    summarized = await summarize_pending(db)
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
