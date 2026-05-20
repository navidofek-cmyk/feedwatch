from datetime import datetime
from pydantic import BaseModel, HttpUrl


class FeedCreate(BaseModel):
    url: str
    name: str
    category: str = "general"


class FeedOut(BaseModel):
    id: int
    url: str
    name: str
    category: str
    active: bool
    created_at: datetime
    last_fetched: datetime | None

    model_config = {"from_attributes": True}


class ArticleOut(BaseModel):
    id: int
    feed_id: int
    title: str
    description: str | None
    url: str
    author: str | None
    published_at: datetime | None
    fetched_at: datetime
    sentiment_score: float | None
    sentiment_label: str | None
    summary: str | None

    model_config = {"from_attributes": True}


class RefreshResult(BaseModel):
    fetched: dict[str, int]
    analyzed: int
    embedded: int
    summarized: int


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
