# feedwatch

**Async RSS aggregator with semantic vector search and Claude AI agents.**

feedwatch fetches your RSS feeds in the background, analyzes how positive or negative each article is, stores everything in a local database, and lets you ask an AI agent questions like *"What happened in AI today?"*

---

## Why feedwatch?

Most RSS readers are just a list. feedwatch is a pipeline:

```
RSS Feed → fetch (async) → SQLite → sentiment → ChromaDB vectors → Claude AI
```

You end up with a searchable, analyzable, AI-queryable knowledge base of everything you read.

---

## Feature overview

| Feature | How |
|---|---|
| ⚡ Async fetching | `httpx` + `asyncio` — all feeds fetched concurrently |
| 🧠 Semantic search | `sentence-transformers` + `ChromaDB` — search by meaning |
| 😊 Sentiment analysis | VADER — every article scored -1 to +1 |
| 🤖 Q&A agent | Claude API with tool use — ask questions, get cited answers |
| 📝 Auto summaries | Claude summarizes each article in 1-2 sentences |
| 🌐 REST API | FastAPI with OpenAPI docs at `/docs` |
| 💎 Rich CLI | Typer + Rich — colored tables, progress spinners |
| 🗄️ Local database | SQLAlchemy async + SQLite — no cloud required |
| ⏰ Auto scheduler | APScheduler — hourly refresh in the background |

---

## Quick demo

```bash
# Add a feed
feedwatch add https://hnrss.org/frontpage --name "Hacker News" --category tech

# Fetch + analyze + embed + summarize
feedwatch refresh

# Ask the AI agent
feedwatch ask "What are people building this week?"

# Semantic search
feedwatch search "machine learning benchmark"

# Top stories by sentiment
feedwatch top --hours 24
```

---

## Tech stack

```
Python 3.11+
├── FastAPI          REST API
├── SQLAlchemy       ORM (async)
├── httpx            Async HTTP
├── feedparser       RSS/Atom parsing
├── sentence-trans.  Local embeddings (all-MiniLM-L6-v2)
├── ChromaDB         Vector database
├── VADER            Sentiment analysis
├── Anthropic SDK    Claude AI agents
├── APScheduler      Background scheduler
├── Typer            CLI framework
└── Rich             Terminal output
```

---

[Get started →](getting-started/installation.md){ .md-button .md-button--primary }
[See all commands →](commands.md){ .md-button }
