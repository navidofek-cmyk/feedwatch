# Quick Start

After [installing](installation.md) and [configuring](configuration.md) feedwatch, here's a complete walkthrough.

---

## 1. Add feeds

```bash
feedwatch add https://hnrss.org/frontpage \
    --name "Hacker News" \
    --category tech

feedwatch add https://feeds.arstechnica.com/arstechnica/index \
    --name "Ars Technica" \
    --category tech

feedwatch add https://www.theverge.com/rss/index.xml \
    --name "The Verge" \
    --category tech
```

Check your feeds:

```bash
feedwatch feeds
```

```
        Feeds
┌────┬──────────────┬──────────┬──────────┬────────┬──────────────────┐
│ ID │ Name         │ Category │ Articles │ Active │ Last fetched     │
├────┼──────────────┼──────────┼──────────┼────────┼──────────────────┤
│ 1  │ Hacker News  │ tech     │ 0        │ ✓      │ never            │
│ 2  │ Ars Technica │ tech     │ 0        │ ✓      │ never            │
│ 3  │ The Verge    │ tech     │ 0        │ ✓      │ never            │
└────┴──────────────┴──────────┴──────────┴────────┴──────────────────┘
```

---

## 2. Refresh

Run the full pipeline — fetch, analyze, embed, summarize:

```bash
feedwatch refresh
```

```
╭─ Refresh complete ─────────╮
│ New articles:   127        │
│ Analyzed:       127        │
│ Embedded:       127        │
│ Summarized:     20         │
╰────────────────────────────╯

Feed           New articles
Hacker News    60
Ars Technica   38
The Verge      29
```

!!! note
    The first refresh downloads the embedding model (~90MB). Subsequent runs are much faster.

---

## 3. Browse articles

```bash
# Last 6 hours, positive articles only
feedwatch list --hours 6 --sentiment positive

# All articles from a specific feed
feedwatch list --feed 1

# Top stories by sentiment score
feedwatch top --hours 24 --num 5
```

---

## 4. Semantic search

Find articles by meaning, not just keywords:

```bash
feedwatch search "open source AI model release"
feedwatch search "electric vehicle battery breakthrough"
feedwatch search "privacy data breach"
```

---

## 5. Ask the AI agent

```bash
feedwatch ask "What are the biggest stories in tech today?"
feedwatch ask "Is the sentiment around AI mostly positive or negative lately?"
feedwatch ask "Are there any articles about Python?"
```

The agent decides which tools to call, searches your local database, and responds with cited sources.

---

## 6. Start the API

```bash
feedwatch serve
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive API explorer.

---

## 7. Auto-refresh

When the API server is running (`feedwatch serve`), APScheduler automatically refreshes all feeds every 60 minutes (configurable via `SCHEDULER_INTERVAL_MINUTES` in `.env`).
