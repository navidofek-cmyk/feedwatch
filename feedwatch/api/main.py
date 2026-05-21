from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from feedwatch.db import init_db
from feedwatch.services.scheduler import get_scheduler
from feedwatch.api.routes import feeds_router, articles_router, actions_router, chat_router, live_router, terminal_router

WEB_DIR = Path(__file__).parent.parent / "web"
DOCS_CS_DIR = Path(__file__).parent.parent.parent / "docs_cs"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler = get_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(
    title="feedwatch",
    description="RSS aggregator with semantic search and AI agents",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(feeds_router)
app.include_router(articles_router)
app.include_router(actions_router)
app.include_router(chat_router)
app.include_router(live_router)
app.include_router(terminal_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/docs-cs")
async def docs_cs():
    return FileResponse(DOCS_CS_DIR / "index.html")


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
