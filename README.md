# feedwatch

> Async RSS aggregator with semantic vector search, sentiment analysis, and Claude AI agents.

feedwatch fetches your RSS feeds in the background, analyzes the sentiment of each article, builds a semantic vector index, and lets you ask an AI agent questions like *"What happened in AI today?"*

**[📖 Full documentation →](https://navidofek-cmyk.github.io/feedwatch/)**

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-AI_agents-7c6dfa?logo=anthropic&logoColor=white)
![uv](https://img.shields.io/badge/uv-package_manager-DE5FE9)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What it does

```
RSS Feed
  → fetch (async httpx)        — all feeds in parallel
  → SQLite (SQLAlchemy ORM)    — deduplicated by GUID
  → VADER sentiment            — score −1.0 to +1.0
  → sentence-transformers      — 384-dim vector embedding
  → ChromaDB                   — local vector database
  → Claude API                 — 1–2 sentence summary
  → Claude agent + tool use    — answers questions about your feeds
```

---

## Features

| | Feature | Tech |
|---|---|---|
| ⚡ | **Async fetching** — all feeds fetched concurrently | `httpx` + `asyncio` |
| 🧠 | **Semantic search** — search by meaning, not keywords | `sentence-transformers` + `ChromaDB` |
| 😊 | **Sentiment analysis** — every article scored −1 to +1 | `VADER` |
| 🤖 | **Q&A agent** — ask questions, get answers with sources | `Anthropic SDK` + tool use |
| 📝 | **Auto summaries** — Claude summarizes each article | `Claude API` |
| 🌐 | **REST API** — full CRUD + `/refresh` + `/ask` | `FastAPI` + `Pydantic` |
| 💎 | **Web UI** — dark dashboard, article cards, live search | Vanilla HTML/JS |
| 🗄️ | **Local database** — no cloud required | `SQLAlchemy` async + `aiosqlite` |
| ⏰ | **Auto scheduler** — hourly refresh in background | `APScheduler` |
| 💻 | **Rich CLI** — colored tables, spinners, top charts | `Typer` + `Rich` |

---

## Quick start

```bash
# Install uv (if not already)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install all dependencies
git clone https://github.com/navidofek-cmyk/feedwatch
cd feedwatch
uv sync

# Configure — copy and edit .env
cp .env.example .env
# Add ANTHROPIC_API_KEY for AI features (optional)

# Add feeds
feedwatch add https://hnrss.org/frontpage --name "Hacker News" --category tech
feedwatch add https://feeds.arstechnica.com/arstechnica/index --name "Ars Technica" --category tech
feedwatch add https://www.theverge.com/rss/index.xml --name "The Verge" --category tech

# Run the full pipeline
feedwatch refresh

# Ask the AI agent
feedwatch ask "What are the biggest AI stories today?"

# Open web UI + API
feedwatch serve    # → http://localhost:8000
                   # → http://localhost:8000/docs  (Swagger UI)
```

---

## CLI commands

```bash
feedwatch add <url> --name <name> [--category <cat>]   # add RSS feed
feedwatch remove <id>                                  # remove feed
feedwatch feeds                                        # list all feeds
feedwatch refresh                                      # fetch → analyze → embed → summarize
feedwatch list [--hours 24] [--sentiment positive]     # browse articles
feedwatch top [--hours 24] [--num 10]                  # top positive / negative
feedwatch search "<query>"                             # semantic vector search
feedwatch ask "<question>"                             # ask the AI agent
feedwatch demo                                         # demo with sample data (no API key needed)
feedwatch serve                                        # start web UI + REST API
```

---

## How it works — theory

### Vector embeddings (semantic search)
Each article is converted to a 384-dimensional vector using `all-MiniLM-L6-v2` (sentence-transformers). Similar texts produce similar vectors. When you search, the query is also embedded and ChromaDB returns the closest articles by cosine distance — finding relevant content even if the exact words don't match.

```python
# "Python performance" and "fast Python code" land close in vector space
# even though they share no words
embedding = model.encode("Python performance")
# → [0.12, -0.34, 0.87, ...]  # 384 numbers representing meaning
```

### Sentiment analysis (VADER)
VADER uses a dictionary of words with emotional scores plus rules for negation, punctuation, and capitalization. Returns a compound score from −1.0 (very negative) to +1.0 (very positive). Runs locally, no API key needed.

```python
score("Amazing breakthrough in AI!")   # → +0.82  positive
score("Critical security flaw found")  # → −0.61  negative
score("Meeting scheduled for Tuesday") # → +0.04  neutral
```

### AI agent with tool use
The Q&A agent doesn't receive all articles at once. Instead, Claude is given 4 tools and decides which to call:

```python
tools = [
    "semantic_search(query)"           # → ChromaDB vector search
    "get_recent_articles(hours)"       # → SQLite query
    "get_feed_stats()"                 # → article counts, sentiment breakdown
    "get_articles_by_sentiment(label)" # → filter by positive/negative/neutral
]
# Claude picks tools → gets results → writes answer with citations
```

### Async pipeline
All feeds are fetched concurrently using `asyncio.gather()`:

```python
# Sequential: 50 feeds × 1s = 50s
# Async: all 50 at once ≈ 1s
counts = await asyncio.gather(*[fetch_one(feed, db) for feed in feeds])
```

---

## Project structure

```
feedwatch/
├── feedwatch/
│   ├── models/            # SQLAlchemy ORM — Feed, Article
│   ├── db/                # async engine, session factory
│   ├── services/
│   │   ├── fetcher.py     # async RSS fetch + deduplication
│   │   ├── analyzer.py    # VADER sentiment scoring
│   │   ├── embedder.py    # sentence-transformers + ChromaDB
│   │   └── scheduler.py   # APScheduler background job
│   ├── agents/
│   │   ├── summarizer.py  # Claude — article summaries
│   │   └── qa_agent.py    # Claude — Q&A with tool use
│   ├── api/
│   │   ├── main.py        # FastAPI app, lifespan, static files
│   │   ├── schemas.py     # Pydantic I/O models
│   │   └── routes/        # feeds, articles, actions (refresh/ask)
│   ├── cli/
│   │   ├── app.py         # Typer commands + Rich output
│   │   └── demo.py        # sample data demo
│   └── web/
│       └── index.html     # single-file dark dashboard
├── docs/                  # MkDocs documentation (8 pages)
├── landing/               # static landing page (GitHub Pages)
├── tests/                 # pytest-asyncio test suite
├── mkdocs.yml
└── pyproject.toml
```

---

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web dashboard UI |
| `GET` | `/feeds/` | List all feeds |
| `POST` | `/feeds/` | Add a feed |
| `DELETE` | `/feeds/{id}` | Remove a feed |
| `PATCH` | `/feeds/{id}/toggle` | Toggle active state |
| `GET` | `/articles/` | List articles (filter: feed, sentiment, limit) |
| `GET` | `/articles/search?q=` | Semantic vector search |
| `GET` | `/articles/{id}` | Get single article |
| `POST` | `/refresh` | Run full pipeline |
| `POST` | `/ask` | Ask the AI agent |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |

---

## Configuration

Copy `.env.example` to `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...          # Claude AI features (optional)
CLAUDE_MODEL=claude-sonnet-4-6        # model to use
SCHEDULER_INTERVAL_MINUTES=60         # auto-refresh interval
API_HOST=0.0.0.0                      # bind address
API_PORT=8000                         # port
```

> AI summaries and the Q&A agent require `ANTHROPIC_API_KEY`. All other features (fetching, sentiment, semantic search, web UI, CLI) work without it.

---

## Development

```bash
uv run pytest               # run tests
uv run mkdocs serve         # docs live preview → localhost:8000
uv run mkdocs build         # build docs to site/
```

---

## Tech stack

| Library | Version | Purpose |
|---|---|---|
| `fastapi` | ≥0.111 | REST API |
| `sqlalchemy[asyncio]` | ≥2.0 | ORM + async queries |
| `aiosqlite` | ≥0.20 | Async SQLite driver |
| `httpx` | ≥0.27 | Async HTTP client |
| `feedparser` | ≥6.0 | RSS/Atom parsing |
| `sentence-transformers` | ≥3.0 | Local text embeddings |
| `chromadb` | ≥0.5 | Vector database |
| `vadersentiment` | ≥3.3 | Sentiment analysis |
| `anthropic` | ≥0.30 | Claude AI SDK |
| `apscheduler` | ≥3.10 | Background scheduler |
| `typer` | ≥0.12 | CLI framework |
| `rich` | ≥13.7 | Terminal output |
| `pydantic-settings` | ≥2.3 | Config + validation |
| `uvicorn` | ≥0.30 | ASGI server |

---

## Lines of code

| Type | Lines |
|---|---|
| Python | 1 714 |
| HTML (web UI + landing) | 983 |
| Markdown (docs) | 1 032 |
| Config (TOML/YAML) | 112 |
| **Total** | **~3 840** |

---

## License

MIT — do whatever you want with it.
