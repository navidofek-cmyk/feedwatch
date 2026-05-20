# Configuration

feedwatch is configured via a `.env` file in the project root.

## Setup

```bash
cp .env.example .env
```

Then edit `.env` with your values:

```env title=".env"
ANTHROPIC_API_KEY=sk-ant-...         # (1)
CLAUDE_MODEL=claude-sonnet-4-6       # (2)
SCHEDULER_INTERVAL_MINUTES=60        # (3)
API_HOST=0.0.0.0                     # (4)
API_PORT=8000                        # (5)
```

1. Your Anthropic API key. Only needed for AI summaries and the Q&A agent. All other features work without it.
2. Claude model to use. Defaults to `claude-sonnet-4-6`.
3. How often the background scheduler refreshes all feeds (in minutes).
4. Host for the FastAPI server.
5. Port for the FastAPI server.

---

## All settings

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | `""` | Anthropic API key for Claude agents |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Claude model ID |
| `DATABASE_URL` | `sqlite+aiosqlite:///feedwatch.db` | SQLAlchemy database URL |
| `CHROMA_PATH` | `./chroma_db` | Path for ChromaDB persistent storage |
| `EMBED_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model name |
| `SCHEDULER_INTERVAL_MINUTES` | `60` | Background refresh interval |
| `FETCH_TIMEOUT` | `30` | HTTP timeout per feed (seconds) |
| `API_HOST` | `0.0.0.0` | FastAPI server host |
| `API_PORT` | `8000` | FastAPI server port |

---

## Without an API key

If `ANTHROPIC_API_KEY` is not set:

- `feedwatch refresh` — still fetches, analyzes sentiment, and embeds. Skips summarization.
- `feedwatch ask` — returns a message explaining the key is missing.
- `feedwatch search` — works fully (uses local sentence-transformers, no API needed).
- All other commands — work fully.

---

## Changing the embedding model

The default model `all-MiniLM-L6-v2` is fast and small (~90MB). For better quality at the cost of speed:

```env
EMBED_MODEL=all-mpnet-base-v2
```

!!! warning
    If you change the model after already embedding articles, delete `chroma_db/` and re-run `feedwatch refresh` to re-embed everything with the new model.
