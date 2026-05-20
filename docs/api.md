# REST API

feedwatch exposes a FastAPI REST API. Start it with `feedwatch serve`, then open [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive Swagger UI.

---

## Base URL

```
http://localhost:8000
```

---

## Feeds

### `GET /feeds/`

List all feeds.

**Response:**
```json
[
  {
    "id": 1,
    "url": "https://hnrss.org/frontpage",
    "name": "Hacker News",
    "category": "tech",
    "active": true,
    "created_at": "2026-05-20T10:00:00Z",
    "last_fetched": "2026-05-20T11:00:00Z"
  }
]
```

---

### `POST /feeds/`

Add a new feed.

**Request body:**
```json
{
  "url": "https://hnrss.org/frontpage",
  "name": "Hacker News",
  "category": "tech"
}
```

**Response:** `201 Created` with the created feed object.

**Errors:**
- `409 Conflict` — feed with this URL already exists

---

### `DELETE /feeds/{feed_id}`

Remove a feed and all its articles. Returns `204 No Content`.

---

### `PATCH /feeds/{feed_id}/toggle`

Toggle a feed's `active` status. Returns the updated feed.

---

## Articles

### `GET /articles/`

List articles with optional filters.

**Query params:**

| Param | Type | Description |
|---|---|---|
| `feed_id` | int | Filter by feed |
| `sentiment` | `positive\|negative\|neutral` | Filter by sentiment |
| `limit` | int (max 200) | Number of results (default 50) |
| `offset` | int | Pagination offset (default 0) |

**Response:**
```json
[
  {
    "id": 42,
    "feed_id": 1,
    "title": "New Python 4.0 release",
    "description": "...",
    "url": "https://example.com/article",
    "author": "Jane Doe",
    "published_at": "2026-05-20T09:30:00Z",
    "fetched_at": "2026-05-20T10:00:00Z",
    "sentiment_score": 0.72,
    "sentiment_label": "positive",
    "summary": "Python 4.0 introduces breaking changes..."
  }
]
```

---

### `GET /articles/{article_id}`

Get a single article by ID.

---

## Actions

### `POST /refresh`

Trigger the full pipeline: fetch all feeds → analyze sentiment → embed → summarize.

**Response:**
```json
{
  "fetched": {
    "Hacker News": 12,
    "Ars Technica": 8,
    "The Verge": 5
  },
  "analyzed": 25,
  "embedded": 25,
  "summarized": 20
}
```

---

### `POST /ask`

Ask the Q&A agent a question.

!!! note
    Requires `ANTHROPIC_API_KEY`.

**Request body:**
```json
{
  "question": "What are the biggest stories in AI today?"
}
```

**Response:**
```json
{
  "answer": "Based on your feeds, the biggest AI stories today are:\n\n1. **OpenAI released GPT-5** (positive sentiment)...\n   Source: https://...\n\n2. ..."
}
```

---

## Health

### `GET /health`

```json
{"status": "ok"}
```
