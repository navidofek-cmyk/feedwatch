# AI Agents

feedwatch includes two Claude-powered agents. Both require `ANTHROPIC_API_KEY` to be set.

---

## Summarizer Agent

**File:** `feedwatch/agents/summarizer.py`

Reads each new article's title and description, then writes a 1-2 sentence summary using Claude.

### How it works

```python
system = "You are a news summarizer. Summarize the article in 1-2 sentences. Be factual and concise."

message = await client.messages.create(
    model=settings.claude_model,
    max_tokens=150,
    system=system,
    messages=[{"role": "user", "content": f"Title: {title}\nDescription: {description}"}],
)
```

### When it runs

- During `feedwatch refresh` — processes new articles that have been embedded but not yet summarized
- Batched to 20 articles per run (configurable in code)
- Skips gracefully if `ANTHROPIC_API_KEY` is not set

---

## Q&A Agent

**File:** `feedwatch/agents/qa_agent.py`

An agentic loop that answers questions about your feeds using Claude's **tool use** feature. The agent decides which tools to call, executes them against your local database and ChromaDB, and synthesizes an answer with source citations.

### Tools

The agent has access to 4 tools:

#### `semantic_search`

```json
{
  "name": "semantic_search",
  "description": "Search articles using semantic/vector similarity.",
  "input_schema": {
    "query": "string",
    "n_results": "integer (default 8)"
  }
}
```

Calls `chromadb.Collection.query()` with an embedding of the query. Returns titles, URLs, and sentiment labels sorted by similarity score.

#### `get_recent_articles`

```json
{
  "name": "get_recent_articles",
  "description": "Get the most recent articles from the last N hours.",
  "input_schema": {
    "hours": "integer (default 24)",
    "limit": "integer (default 10)"
  }
}
```

Queries SQLite for articles where `fetched_at >= now - hours`.

#### `get_feed_stats`

```json
{
  "name": "get_feed_stats",
  "description": "Get statistics: article counts per feed, sentiment distribution.",
  "input_schema": {}
}
```

Returns a JSON object with per-feed article counts and global sentiment breakdown.

#### `get_articles_by_sentiment`

```json
{
  "name": "get_articles_by_sentiment",
  "description": "Get articles filtered by sentiment label.",
  "input_schema": {
    "label": "positive | negative | neutral",
    "limit": "integer (default 10)"
  }
}
```

### Agentic loop

The agent runs a standard tool-use loop:

```python
while True:
    response = await client.messages.create(
        model=settings.claude_model,
        tools=TOOLS,
        messages=messages,
    )

    if response.stop_reason == "end_turn":
        return response.content[0].text   # final answer

    if response.stop_reason == "tool_use":
        # execute all requested tools
        tool_results = [await _run_tool(block.name, block.input, db)
                        for block in response.content
                        if block.type == "tool_use"]
        # feed results back to Claude
        messages.append({"role": "user", "content": tool_results})
```

### Example conversation

**Question:** *"What is the general mood in tech news today?"*

Claude might:

1. Call `get_feed_stats()` → sees 127 articles, 52 positive, 31 negative, 44 neutral
2. Call `get_recent_articles(hours=24)` → gets a sample of today's articles
3. Call `semantic_search("major tech announcements")` → finds the biggest stories
4. Return a summary with sentiment breakdown and specific article citations

---

## Prompt caching

For high-volume use, you can enable Anthropic's prompt caching on the system prompt to reduce latency and cost. Add `cache_control` to the system message:

```python
system=[{
    "type": "text",
    "text": "You are a news research assistant...",
    "cache_control": {"type": "ephemeral"}
}]
```
