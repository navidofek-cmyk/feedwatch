# feedwatch

> Async RSS aggregator with semantic vector search and Claude AI agents.

feedwatch fetches your RSS feeds in the background, analyzes the sentiment of each article, stores everything locally, and lets you ask an AI agent questions like *"What happened in AI today?"*

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green?logo=fastapi)
![License](https://img.shields.io/badge/license-MIT-purple)

## Features

- ⚡ **Async fetching** — all feeds fetched concurrently with `httpx`
- 🧠 **Semantic search** — `sentence-transformers` + `ChromaDB` vector database
- 😊 **Sentiment analysis** — every article scored -1 to +1 with VADER
- 🤖 **Q&A agent** — Claude AI with tool use answers questions about your feeds
- 📝 **Auto summaries** — Claude summarizes each article in 1-2 sentences
- 🌐 **REST API** — FastAPI with auto-generated Swagger docs
- 💎 **Rich CLI** — colored tables, progress spinners, top article charts
- 🗄️ **Local database** — SQLAlchemy async + SQLite, no cloud required
- ⏰ **Auto scheduler** — APScheduler refreshes feeds every hour

## Quick start

```bash
# Install uv (if not already)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/yourname/feedwatch
cd feedwatch
uv sync

# Configure (add your Anthropic API key)
cp .env.example .env

# Add a feed and refresh
feedwatch add https://hnrss.org/frontpage --name "Hacker News"
feedwatch refresh

# Ask the AI agent
feedwatch ask "What are the biggest stories today?"

# Start the web UI + API
feedwatch serve        # → http://localhost:8000
```

## CLI commands

| Command | Description |
|---|---|
| `feedwatch add <url> --name <n>` | Add a new RSS feed |
| `feedwatch feeds` | List all feeds |
| `feedwatch refresh` | Fetch → analyze → embed → summarize |
| `feedwatch list --hours 6 --sentiment positive` | Browse articles |
| `feedwatch top` | Top positive / negative articles |
| `feedwatch search <query>` | Semantic vector search |
| `feedwatch ask <question>` | Ask the AI agent |
| `feedwatch demo` | Run demo with sample data (no API key needed) |
| `feedwatch serve` | Start REST API + web UI |

## Tech stack

```
Python 3.11+  ·  FastAPI  ·  SQLAlchemy (async)  ·  httpx  ·  feedparser
sentence-transformers  ·  ChromaDB  ·  VADER  ·  Anthropic SDK
APScheduler  ·  Typer  ·  Rich  ·  uv
```

## Development

```bash
uv run pytest          # run tests
uv run mkdocs serve    # docs at http://localhost:8000
```

## License

MIT
