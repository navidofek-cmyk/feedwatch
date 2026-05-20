"""
feedwatch start — combined server + interactive REPL + live SSE broadcast.

Spustí FastAPI server v background threadu a otevře interaktivní CLI
kde můžeš psát příkazy přímo. Prohlížeč dostává live SSE updaty.

Ctrl+C nebo příkaz 'quit' server zastaví.
"""
import asyncio
import threading
import sys
from datetime import datetime, UTC

import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.live import Live
from rich.text import Text

console = Console()

HELP = """
[bold cyan]feedwatch REPL commands:[/bold cyan]
  [cyan]refresh[/cyan]          fetch new articles from all feeds
  [cyan]feeds[/cyan]            list all feeds
  [cyan]list[/cyan]             show recent articles
  [cyan]top[/cyan]              top positive / negative articles
  [cyan]search <query>[/cyan]   semantic search
  [cyan]add <url> <name>[/cyan] add RSS feed
  [cyan]stats[/cyan]            quick stats
  [cyan]help[/cyan]             show this help
  [cyan]quit[/cyan] / Ctrl+C   stop server and exit
"""


class FeedwatchREPL:
    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        self.host = host
        self.port = port
        self._server_thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self._running = True

    def _start_server(self):
        from feedwatch.api.main import app
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._server.run()

    def start_server(self):
        self._server_thread = threading.Thread(
            target=self._start_server,
            daemon=True,
            name="feedwatch-server",
        )
        self._server_thread.start()

    def stop(self):
        self._running = False
        if self._server:
            self._server.should_exit = True

    async def _run_command(self, cmd: str) -> None:
        from feedwatch.db import init_db, AsyncSessionLocal
        from feedwatch.api.routes.live import broadcast

        parts = cmd.strip().split(maxsplit=2)
        if not parts:
            return
        verb = parts[0].lower()

        if verb in ("quit", "exit", "q"):
            console.print("[yellow]Stopping server...[/yellow]")
            self.stop()
            return

        if verb == "help":
            console.print(HELP)
            return

        await init_db()

        if verb == "refresh":
            from feedwatch.services.fetcher import fetch_all
            from feedwatch.services.analyzer import analyze_pending
            from feedwatch.services.embedder import embed_pending
            from feedwatch.agents.summarizer import summarize_pending

            async with AsyncSessionLocal() as db:
                broadcast("status", {"msg": "🔄 Fetching feeds..."})
                console.print("[dim]Fetching...[/dim]", end=" ")
                fetched = await fetch_all(db)

                broadcast("status", {"msg": "😊 Analyzing sentiment..."})
                console.print("[dim]Analyzing...[/dim]", end=" ")
                analyzed = await analyze_pending(db)

                broadcast("status", {"msg": "🧠 Embedding..."})
                console.print("[dim]Embedding...[/dim]", end=" ")
                embedded = await embed_pending(db)

                broadcast("status", {"msg": "✍️ Summarizing..."})
                summarized = await summarize_pending(db)

                total = sum(fetched.values())
                broadcast("refresh_done", {
                    "total": total, "analyzed": analyzed,
                    "embedded": embedded, "summarized": summarized,
                    "feeds": fetched,
                })

            console.print(
                f"\n[green]✓[/green] {total} new · {analyzed} analyzed · {embedded} embedded · {summarized} summarized"
            )

        elif verb == "feeds":
            from sqlalchemy import select, func
            from feedwatch.models.feed import Feed
            from feedwatch.models.article import Article
            from rich.table import Table
            from rich import box

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Feed, func.count(Article.id))
                    .outerjoin(Article).group_by(Feed.id).order_by(Feed.name)
                )
                rows = result.all()

            t = Table(box=box.SIMPLE, highlight=True)
            t.add_column("ID", style="dim", width=4)
            t.add_column("Name", style="bold cyan")
            t.add_column("Category", style="magenta")
            t.add_column("Articles", justify="right")
            t.add_column("Last fetched", style="dim")
            for feed, count in rows:
                last = feed.last_fetched.strftime("%m-%d %H:%M") if feed.last_fetched else "never"
                t.add_row(str(feed.id), feed.name, feed.category, str(count), last)
            console.print(t)

        elif verb == "list":
            from sqlalchemy import select
            from feedwatch.models.article import Article
            from rich.table import Table
            from rich import box
            from rich.text import Text

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Article).order_by(Article.fetched_at.desc()).limit(15)
                )
                articles = result.scalars().all()

            if not articles:
                console.print("[dim]No articles yet. Run: refresh[/dim]")
                return

            STYLES = {"positive": "green", "negative": "red", "neutral": "yellow"}
            t = Table(box=box.SIMPLE, show_lines=False)
            t.add_column("Title", max_width=55)
            t.add_column("Sentiment", justify="center", width=12)
            t.add_column("Score", justify="right", width=7)
            for a in articles:
                style = STYLES.get(a.sentiment_label or "", "dim")
                t.add_row(
                    a.title[:55],
                    Text(a.sentiment_label or "?", style=style),
                    Text(f"{a.sentiment_score:+.2f}" if a.sentiment_score else "—", style=style),
                )
            console.print(t)

        elif verb == "top":
            from sqlalchemy import select
            from feedwatch.models.article import Article
            from rich.table import Table
            from rich import box

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Article)
                    .where(Article.sentiment_score.isnot(None))
                    .order_by(Article.sentiment_score.desc())
                    .limit(20)
                )
                articles = result.scalars().all()

            positives = [a for a in articles if a.sentiment_label == "positive"][:5]
            negatives = sorted(
                [a for a in articles if a.sentiment_label == "negative"],
                key=lambda x: x.sentiment_score,
            )[:5]

            for items, title, color in [(positives, "Top Positive", "green"), (negatives, "Top Negative", "red")]:
                t = Table(title=title, box=box.SIMPLE_HEAVY, border_style=color)
                t.add_column("Score", width=7, style=color, justify="right")
                t.add_column("Title", max_width=60)
                for a in items:
                    t.add_row(f"{a.sentiment_score:+.2f}", a.title[:60])
                console.print(t)

        elif verb == "search":
            query = " ".join(parts[1:]) if len(parts) > 1 else ""
            if not query:
                console.print("[red]Usage: search <query>[/red]")
                return
            from feedwatch.services.embedder import semantic_search
            from rich.table import Table
            from rich import box
            from rich.text import Text

            results = semantic_search(query, n_results=8)
            if not results:
                console.print("[dim]No results.[/dim]")
                return

            STYLES = {"positive": "green", "negative": "red", "neutral": "yellow"}
            t = Table(title=f'Search: "{query}"', box=box.SIMPLE)
            t.add_column("Score", width=6, justify="right")
            t.add_column("Title", max_width=55)
            t.add_column("Sentiment", width=10, justify="center")
            for r in results:
                m = r["metadata"]
                style = STYLES.get(m.get("sentiment_label", ""), "dim")
                t.add_row(
                    f"{r['score']:.2f}",
                    m["title"][:55],
                    Text(m.get("sentiment_label", "?"), style=style),
                )
            console.print(t)

        elif verb == "add":
            if len(parts) < 3:
                console.print("[red]Usage: add <url> <name>[/red]")
                return
            url, name = parts[1], parts[2]
            from sqlalchemy import select
            from feedwatch.models.feed import Feed

            async with AsyncSessionLocal() as db:
                existing = (await db.execute(select(Feed).where(Feed.url == url))).scalar_one_or_none()
                if existing:
                    console.print(f"[yellow]Feed already exists:[/yellow] {url}")
                    return
                feed = Feed(url=url, name=name, category="general")
                db.add(feed)
                await db.commit()
                broadcast("feed_added", {"name": name, "url": url})
            console.print(f"[green]Added:[/green] [bold]{name}[/bold]")

        elif verb == "stats":
            from sqlalchemy import select, func
            from feedwatch.models.article import Article
            from feedwatch.models.feed import Feed

            async with AsyncSessionLocal() as db:
                total = (await db.execute(select(func.count(Article.id)))).scalar()
                feeds = (await db.execute(select(func.count(Feed.id)))).scalar()
                sentiment = (await db.execute(
                    select(Article.sentiment_label, func.count(Article.id)).group_by(Article.sentiment_label)
                )).all()

            s = {lbl or "unknown": cnt for lbl, cnt in sentiment}
            console.print(
                f"[cyan]Feeds:[/cyan] {feeds}  "
                f"[cyan]Articles:[/cyan] {total}  "
                f"[green]Positive:[/green] {s.get('positive',0)}  "
                f"[red]Negative:[/red] {s.get('negative',0)}  "
                f"[yellow]Neutral:[/yellow] {s.get('neutral',0)}"
            )
        else:
            console.print(f"[dim]Unknown command: {verb}. Type [bold]help[/bold] for list.[/dim]")

    async def run_repl(self):
        console.print(HELP)

        while self._running:
            try:
                # async stdin read
                loop = asyncio.get_event_loop()
                line = await loop.run_in_executor(
                    None,
                    lambda: input("\n[feedwatch]> ") if self._running else None,
                )
                if line is None:
                    break
                line = line.strip()
                if not line:
                    continue
                await self._run_command(line)
                if not self._running:
                    break
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Stopping...[/yellow]")
                self.stop()
                break
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")


async def run_start(host: str, port: int):
    repl = FeedwatchREPL(host=host, port=port)

    console.print(Panel(
        f"[bold green]feedwatch[/bold green] starting...\n\n"
        f"[cyan]Web UI:[/cyan]  http://{host}:{port}\n"
        f"[cyan]API docs:[/cyan] http://{host}:{port}/docs\n"
        f"[cyan]Live SSE:[/cyan] http://{host}:{port}/live\n\n"
        f"[dim]Browser stays connected — refresh/add commands push live updates[/dim]",
        border_style="cyan",
    ))

    # start server in background thread
    repl.start_server()

    # wait for server to be ready
    import httpx
    for _ in range(30):
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(f"http://localhost:{port}/health", timeout=1)
                if r.status_code == 200:
                    console.print("[green]✓[/green] Server ready")
                    break
        except Exception:
            await asyncio.sleep(0.5)

    # run REPL
    await repl.run_repl()
    console.print("[dim]Server stopped.[/dim]")
