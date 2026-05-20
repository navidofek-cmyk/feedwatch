# Installation

feedwatch requires **Python 3.11+** and [uv](https://docs.astral.sh/uv/).

## Install uv

If you don't have `uv` yet:

=== "Linux / macOS"
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

=== "Windows"
    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "pip"
    ```bash
    pip install uv
    ```

---

## Clone and install

```bash
git clone https://github.com/yourname/feedwatch
cd feedwatch

# Create venv + install all dependencies in one command
uv sync
```

That's it. `uv sync` reads `pyproject.toml`, creates `.venv/`, and installs everything — including dev dependencies.

---

## Verify

```bash
uv run feedwatch --help
```

You should see the feedwatch command tree:

```
 Usage: feedwatch [OPTIONS] COMMAND [ARGS]...

 feedwatch — RSS aggregator with AI agents

╭─ Commands ──────────────────────────────────────────────╮
│ add       Add a new RSS feed.                           │
│ remove    Remove a feed and all its articles.           │
│ feeds     List all feeds.                               │
│ refresh   Fetch → analyze → embed → summarize.         │
│ list      List articles.                                │
│ top       Show top positive and negative articles.      │
│ search    Semantic search over articles.                │
│ ask       Ask the AI agent a question.                  │
│ serve     Start the FastAPI server.                     │
╰─────────────────────────────────────────────────────────╯
```

---

## Running commands

With `uv`, you don't need to activate the venv manually:

```bash
# Option 1: prefix every command with uv run
uv run feedwatch refresh

# Option 2: activate the venv once, then use feedwatch directly
source .venv/bin/activate   # Linux/macOS
# or
.venv\Scripts\activate      # Windows

feedwatch refresh
```

---

## Running tests

```bash
uv run pytest
```

---

## Building the docs

```bash
# Live preview at http://localhost:8000
uv run mkdocs serve

# Build static site to site/
uv run mkdocs build
```

---

Next: [Configuration →](configuration.md)
