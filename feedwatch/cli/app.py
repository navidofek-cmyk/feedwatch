import asyncio
from datetime import datetime, UTC, timedelta

import typer
from rich.console import Console
from rich.table import Table
from rich import box
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(help="feedwatch — RSS aggregator with AI agents", no_args_is_help=True)
console = Console()

SENTIMENT_STYLE = {
    "positive": "green",
    "negative": "red",
    "neutral": "yellow",
    None: "dim",
}


def _run(coro):
    return asyncio.run(coro)


async def _get_db():
    from feedwatch.db import init_db, AsyncSessionLocal
    await init_db()
    return AsyncSessionLocal()


@app.command()
def add(
    url: str = typer.Argument(..., help="RSS feed URL"),
    name: str = typer.Option(..., "--name", "-n", help="Feed display name"),
    category: str = typer.Option("general", "--category", "-c", help="Category"),
):
    """Add a new RSS feed."""
    async def _add():
        from sqlalchemy import select
        from feedwatch.models.feed import Feed

        async with await _get_db() as db:
            existing = await db.execute(select(Feed).where(Feed.url == url))
            if existing.scalar_one_or_none():
                console.print(f"[yellow]Feed already exists:[/yellow] {url}")
                raise typer.Exit(1)
            feed = Feed(url=url, name=name, category=category)
            db.add(feed)
            await db.commit()
            console.print(f"[green]Added:[/green] [bold]{name}[/bold] ({category})")

    _run(_add())


@app.command()
def remove(feed_id: int = typer.Argument(..., help="Feed ID to remove")):
    """Remove a feed and all its articles."""
    async def _remove():
        async with await _get_db() as db:
            from feedwatch.models.feed import Feed
            feed = await db.get(Feed, feed_id)
            if not feed:
                console.print(f"[red]Feed {feed_id} not found.[/red]")
                raise typer.Exit(1)
            await db.delete(feed)
            await db.commit()
            console.print(f"[red]Removed:[/red] {feed.name}")

    _run(_remove())


@app.command()
def feeds():
    """List all feeds."""
    async def _feeds():
        from sqlalchemy import select, func
        from feedwatch.models.feed import Feed
        from feedwatch.models.article import Article

        async with await _get_db() as db:
            result = await db.execute(
                select(Feed, func.count(Article.id))
                .outerjoin(Article)
                .group_by(Feed.id)
                .order_by(Feed.name)
            )
            rows = result.all()

        table = Table(title="Feeds", box=box.ROUNDED, highlight=True)
        table.add_column("ID", style="dim", width=5)
        table.add_column("Name", style="bold cyan")
        table.add_column("Category", style="magenta")
        table.add_column("Articles", justify="right")
        table.add_column("Active", justify="center")
        table.add_column("Last fetched", style="dim")

        for feed, count in rows:
            active = "[green]✓[/green]" if feed.active else "[red]✗[/red]"
            last = feed.last_fetched.strftime("%Y-%m-%d %H:%M") if feed.last_fetched else "never"
            table.add_row(str(feed.id), feed.name, feed.category, str(count), active, last)

        console.print(table)

    _run(_feeds())


@app.command()
def refresh():
    """Fetch new articles from all feeds, analyze, embed, summarize."""
    async def _refresh():
        from feedwatch.db import init_db, AsyncSessionLocal
        from feedwatch.services.fetcher import fetch_all
        from feedwatch.services.analyzer import analyze_pending
        from feedwatch.services.embedder import embed_pending
        from feedwatch.agents.summarizer import summarize_pending

        await init_db()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            async with AsyncSessionLocal() as db:
                task = progress.add_task("Fetching feeds...", total=None)
                fetched = await fetch_all(db)
                total_new = sum(fetched.values())

                progress.update(task, description="Analyzing sentiment...")
                analyzed = await analyze_pending(db)

                progress.update(task, description="Embedding articles...")
                embedded = await embed_pending(db)

                progress.update(task, description="Summarizing with AI...")
                summarized = await summarize_pending(db)

                progress.update(task, description="Done!", completed=True)

        console.print()
        console.print(Panel(
            f"[green]New articles:[/green] {total_new}\n"
            f"[cyan]Analyzed:[/cyan] {analyzed}\n"
            f"[blue]Embedded:[/blue] {embedded}\n"
            f"[magenta]Summarized:[/magenta] {summarized}",
            title="Refresh complete",
            border_style="green",
        ))

        if fetched:
            table = Table(box=box.SIMPLE)
            table.add_column("Feed")
            table.add_column("New articles", justify="right")
            for name, count in sorted(fetched.items(), key=lambda x: -x[1]):
                table.add_row(name, str(count))
            console.print(table)

    _run(_refresh())


@app.command()
def list(
    feed_id: int | None = typer.Option(None, "--feed", "-f", help="Filter by feed ID"),
    sentiment: str | None = typer.Option(None, "--sentiment", "-s", help="positive/negative/neutral"),
    hours: int = typer.Option(24, "--hours", "-h", help="Last N hours"),
    limit: int = typer.Option(20, "--limit", "-l"),
):
    """List articles."""
    async def _list():
        from sqlalchemy import select
        from feedwatch.models.article import Article

        since = datetime.now(UTC) - timedelta(hours=hours)
        async with await _get_db() as db:
            q = (
                select(Article)
                .where(Article.fetched_at >= since)
                .order_by(Article.fetched_at.desc())
                .limit(limit)
            )
            if feed_id:
                q = q.where(Article.feed_id == feed_id)
            if sentiment:
                q = q.where(Article.sentiment_label == sentiment)
            result = await db.execute(q)
            articles = result.scalars().all()

        if not articles:
            console.print("[dim]No articles found.[/dim]")
            return

        table = Table(
            title=f"Articles (last {hours}h)", box=box.ROUNDED, show_lines=True
        )
        table.add_column("ID", style="dim", width=6)
        table.add_column("Title", max_width=55)
        table.add_column("Sentiment", justify="center", width=10)
        table.add_column("Published", width=16)
        table.add_column("Summary", max_width=40, style="dim")

        for a in articles:
            style = SENTIMENT_STYLE.get(a.sentiment_label, "")
            sentiment_cell = Text(a.sentiment_label or "?", style=style)
            pub = a.published_at.strftime("%m-%d %H:%M") if a.published_at else ""
            summary = (a.summary or "")[:80]
            table.add_row(str(a.id), a.title[:55], sentiment_cell, pub, summary)

        console.print(table)

    _run(_list())


@app.command()
def top(
    hours: int = typer.Option(24, "--hours", "-h", help="Last N hours"),
    n: int = typer.Option(10, "--num", "-n", help="Number of top articles"),
):
    """Show top positive and negative articles."""
    async def _top():
        from sqlalchemy import select
        from feedwatch.models.article import Article

        since = datetime.now(UTC) - timedelta(hours=hours)
        async with await _get_db() as db:
            result = await db.execute(
                select(Article)
                .where(Article.fetched_at >= since)
                .where(Article.sentiment_score != None)  # noqa: E711
                .order_by(Article.sentiment_score.desc())
                .limit(n * 2)
            )
            articles = result.scalars().all()

        if not articles:
            console.print("[dim]No articles with sentiment data.[/dim]")
            return

        positive = [a for a in articles if a.sentiment_label == "positive"][:n]
        negative = sorted(
            [a for a in articles if a.sentiment_label == "negative"],
            key=lambda x: x.sentiment_score,
        )[:n]

        def _section(items, title, color):
            t = Table(title=title, box=box.SIMPLE_HEAVY, border_style=color)
            t.add_column("Score", width=7, justify="right")
            t.add_column("Title", max_width=60)
            t.add_column("URL", style="dim", max_width=40)
            for a in items:
                t.add_row(
                    f"{a.sentiment_score:+.2f}",
                    a.title[:60],
                    a.url[:40],
                )
            console.print(t)

        _section(positive, f"Top {len(positive)} Positive", "green")
        _section(negative, f"Top {len(negative)} Negative", "red")

    _run(_top())


@app.command()
def ask(question: str = typer.Argument(..., help="Question to ask the AI agent")):
    """Ask the AI agent a question about your feeds."""
    async def _ask():
        from feedwatch.db import init_db, AsyncSessionLocal
        from feedwatch.agents.qa_agent import ask as agent_ask

        await init_db()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Thinking...", total=None)
            async with AsyncSessionLocal() as db:
                answer = await agent_ask(question, db)

        console.print(Panel(answer, title="[bold cyan]AI Answer[/bold cyan]", border_style="cyan"))

    _run(_ask())


@app.command()
def search(query: str = typer.Argument(..., help="Semantic search query")):
    """Semantic search over articles."""
    from feedwatch.services.embedder import semantic_search as sem_search

    results = sem_search(query, n_results=10)
    if not results:
        console.print("[dim]No results.[/dim]")
        return

    table = Table(title=f'Search: "{query}"', box=box.ROUNDED)
    table.add_column("Score", width=7, justify="right")
    table.add_column("Title", max_width=55)
    table.add_column("Sentiment", width=10, justify="center")
    table.add_column("URL", style="dim", max_width=35)

    for r in results:
        meta = r["metadata"]
        style = SENTIMENT_STYLE.get(meta.get("sentiment_label"), "")
        sentiment_cell = Text(meta.get("sentiment_label", "?"), style=style)
        table.add_row(
            f"{r['score']:.2f}",
            meta["title"][:55],
            sentiment_cell,
            meta["url"][:35],
        )

    console.print(table)


@app.command()
def demo():
    """Run an interactive demo with sample data. No API key or network required."""
    from feedwatch.cli.demo import run_demo
    run_demo()


@app.command()
def autism():
    """Add preset autism/PAS community feeds (Reddit, forums, organizations)."""
    async def _autism():
        from feedwatch.db import init_db, AsyncSessionLocal
        from feedwatch.services.scraper import add_autism_feeds, REDDIT_AUTISM_FEEDS

        await init_db()
        async with AsyncSessionLocal() as db:
            with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as p:
                t = p.add_task("Adding autism community feeds...", total=None)
                added = await add_autism_feeds(db)
                p.update(t, description="Done!")

        console.print()
        console.print(Panel(
            f"[green]Added {added} new feeds[/green]\n\n" +
            "\n".join(f"  [cyan]•[/cyan] {f['name']} [dim]({f['category']})[/dim]"
                      for f in REDDIT_AUTISM_FEEDS),
            title="[bold]Autism / PAS community feeds[/bold]",
            border_style="cyan",
        ))
        console.print()
        console.print("[dim]Now run:[/dim] [bold cyan]feedwatch refresh[/bold cyan] [dim]to fetch posts[/dim]")

    _run(_autism())


@app.command()
def forums(
    question: str = typer.Argument(
        "What are parents of autistic children discussing most?",
        help="Question for the forum digest agent"
    ),
):
    """Ask the AI agent about parent forum discussions (autism/PAS community)."""
    async def _forums():
        from feedwatch.db import init_db, AsyncSessionLocal
        from feedwatch.agents.forum_agent import digest

        await init_db()
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console, transient=True) as p:
            p.add_task("Reading forum discussions...", total=None)
            async with AsyncSessionLocal() as db:
                answer = await digest(question, db)

        console.print()
        console.print(Panel(
            answer,
            title="[bold cyan]Forum digest — parent community[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        ))

    _run(_forums())


@app.command()
def start(
    host: str = typer.Option("0.0.0.0", "--host", "-H"),
    port: int = typer.Option(8000, "--port", "-p"),
    api_key: str = typer.Option("", "--api-key", "-k", help="Anthropic API key"),
    with_claude: bool = typer.Option(False, "--claude", "-c", help="Launch claude CLI with feedwatch MCP"),
):
    """Start web server + optionally launch claude CLI with feedwatch MCP tools."""
    import os, asyncio, subprocess, json, tempfile, threading, time
    from pathlib import Path

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key
        from feedwatch.config import settings
        settings.anthropic_api_key = key
        console.print("[green]✓[/green] API key set")

    project_dir = str(Path(__file__).parent.parent.parent)

    if with_claude:
        # 1. nastartuj web server na pozadí
        from feedwatch.cli.repl import ServerThread
        server = ServerThread(host, port)
        server.start()

        # počkej na start
        import httpx
        for _ in range(20):
            try:
                import urllib.request
                urllib.request.urlopen(f"http://localhost:{port}/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)

        console.print(Panel(
            f"[bold green]feedwatch server[/bold green] → http://{host}:{port}\n"
            f"[dim]Web UI:[/dim] http://{host}:{port}\n"
            f"[dim]Docs:[/dim]   http://{host}:{port}/docs\n\n"
            f"[bold cyan]Spouštím claude s feedwatch MCP nástroji...[/bold cyan]\n"
            f"[dim]Nástroje: fw_search, fw_recent, fw_ask, fw_feeds, fw_stats, fw_refresh, fw_top, fw_forums[/dim]",
            border_style="cyan",
        ))

        # 2. MCP config jako env var pro claude
        mcp_config = {
            "feedwatch": {
                "command": "uv",
                "args": ["run", "feedwatch-mcp"],
                "cwd": project_dir,
            }
        }

        env = os.environ.copy()
        env["MCP_SERVERS"] = json.dumps(mcp_config)

        # 3. spusť claude CLI — přebere terminál
        try:
            subprocess.run(
                ["claude", "--mcp-config", json.dumps({"mcpServers": mcp_config})],
                env=env,
                cwd=project_dir,
            )
        except FileNotFoundError:
            # claude není v PATH — zkus jiné varianty
            for cmd in [["npx", "@anthropic-ai/claude-code"], ["claude-code"]]:
                try:
                    subprocess.run(cmd + ["--mcp-config", json.dumps({"mcpServers": mcp_config})],
                                   env=env, cwd=project_dir)
                    break
                except FileNotFoundError:
                    continue
            else:
                console.print("[yellow]claude CLI nenalezeno.[/yellow]")
                console.print(f"[dim]Spusť ručně v novém terminálu:[/dim]")
                console.print(f"[cyan]FEEDWATCH_DIR={project_dir} claude[/cyan]")
                console.print("\n[dim]Server stále běží. Ctrl+C pro ukončení.[/dim]")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass

        server.stop()
    else:
        # původní chování — jen REPL
        asyncio.run(__import__('feedwatch.cli.repl', fromlist=['run_start']).run_start(host, port))


@app.command()
def mcp():
    """Start the MCP server (stdio) for Claude Code / Codex integration."""
    import asyncio
    from feedwatch.mcp_server import run as mcp_run

    config_example = """\
Add to ~/.claude/settings.json:

{
  "mcpServers": {
    "feedwatch": {
      "command": "uv",
      "args": ["run", "feedwatch-mcp"],
      "cwd": "/ABSOLUTE/PATH/TO/feedwatch"
    }
  }
}

Then in Claude Code you can ask:
  "Search my feeds for VOKS discussions"
  "What are autism parents talking about on Reddit?"
  "Summarize today's news from my feeds"
"""
    console.print(Panel(config_example, title="[bold cyan]feedwatch MCP server[/bold cyan]", border_style="cyan"))
    asyncio.run(mcp_run())


@app.command()
def serve(
    api_key: str = typer.Option("", "--api-key", "-k", help="Anthropic API key"),
):
    """Start the FastAPI server."""
    import os, uvicorn
    from feedwatch.config import settings

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key
        settings.anthropic_api_key = key
        console.print("[green]✓[/green] API key set")

    console.print(Panel(
        f"[bold green]feedwatch API[/bold green]\n"
        f"http://{settings.api_host}:{settings.api_port}/docs",
        border_style="green",
    ))
    uvicorn.run(
        "feedwatch.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
