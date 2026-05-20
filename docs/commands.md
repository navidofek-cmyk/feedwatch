# CLI Commands

All commands are available via `feedwatch`. Run `feedwatch --help` or `feedwatch <command> --help` for full options.

---

## `feedwatch add`

Add a new RSS feed.

```bash
feedwatch add <url> --name <name> [--category <category>]
```

| Option | Short | Default | Description |
|---|---|---|---|
| `--name` | `-n` | required | Display name for the feed |
| `--category` | `-c` | `general` | Category label |

**Example:**
```bash
feedwatch add https://hnrss.org/frontpage --name "Hacker News" --category tech
```

---

## `feedwatch remove`

Remove a feed and all its articles.

```bash
feedwatch remove <feed_id>
```

Get the feed ID from `feedwatch feeds`.

---

## `feedwatch feeds`

List all feeds with article counts and status.

```bash
feedwatch feeds
```

---

## `feedwatch refresh`

Run the full processing pipeline on all active feeds:

1. Fetch new articles (async, all feeds in parallel)
2. Analyze sentiment (VADER)
3. Embed into ChromaDB (sentence-transformers)
4. Summarize with Claude (if API key is set)

```bash
feedwatch refresh
```

---

## `feedwatch list`

List articles with optional filters.

```bash
feedwatch list [--feed <id>] [--sentiment <label>] [--hours <n>] [--limit <n>]
```

| Option | Short | Default | Description |
|---|---|---|---|
| `--feed` | `-f` | all | Filter by feed ID |
| `--sentiment` | `-s` | all | `positive`, `negative`, or `neutral` |
| `--hours` | `-h` | `24` | Only articles from the last N hours |
| `--limit` | `-l` | `20` | Max number of results |

**Examples:**
```bash
# Last 6 hours, positive only
feedwatch list --hours 6 --sentiment positive

# All articles from feed 2, last 48 hours
feedwatch list --feed 2 --hours 48 --limit 50
```

---

## `feedwatch top`

Show the most positive and most negative articles from a time window.

```bash
feedwatch top [--hours <n>] [--num <n>]
```

| Option | Short | Default | Description |
|---|---|---|---|
| `--hours` | `-h` | `24` | Time window |
| `--num` | `-n` | `10` | Number of articles per section |

---

## `feedwatch search`

Semantic vector search — finds articles by meaning, not just word matching.

```bash
feedwatch search "<query>"
```

**Examples:**
```bash
feedwatch search "quantum computing breakthrough"
feedwatch search "startup fundraising series A"
feedwatch search "open source language model"
```

---

## `feedwatch ask`

Ask the AI agent (Claude) a question about your feeds. The agent searches your local database and responds with source citations.

```bash
feedwatch ask "<question>"
```

!!! note
    Requires `ANTHROPIC_API_KEY` to be set in `.env`.

**Examples:**
```bash
feedwatch ask "What are the biggest AI stories this week?"
feedwatch ask "Is sentiment around cryptocurrencies positive or negative lately?"
feedwatch ask "Are there any articles about Python 4?"
feedwatch ask "Summarize what happened in tech today."
```

---

## `feedwatch serve`

Start the FastAPI REST API server. Opens `http://localhost:8000/docs` for interactive API exploration.

```bash
feedwatch serve
```

The server also runs the background scheduler — feeds are automatically refreshed every hour.
