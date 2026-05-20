"""
feedwatch start — server + REPL paralelně.

Server běží v background threadu, REPL v popředí.
Prohlížeč je připojený přes SSE a dostává live updaty.
Ctrl+C nebo 'quit' ukončí vše.
"""
import asyncio
import threading

import uvicorn
from rich.console import Console
from rich.panel import Panel

console = Console()

HELP = """
[bold cyan]Příkazy:[/bold cyan]

  [bold]Lokální databáze[/bold]
  [cyan]refresh[/cyan]                 stáhnout nové články ze všech feedů
  [cyan]feeds[/cyan]                   seznam feedů
  [cyan]list[/cyan]                    poslední články
  [cyan]top[/cyan]                     nejlepší / nejhorší články
  [cyan]search[/cyan] <dotaz>          sémantické hledání v databázi
  [cyan]add[/cyan] <url> <název>       přidat RSS feed
  [cyan]stats[/cyan]                   rychlá statistika

  [bold]Web[/bold]
  [cyan]websearch[/cyan] <dotaz>       hledat na internetu (DuckDuckGo)
  [cyan]webnews[/cyan] <dotaz>         hledat novinky na internetu
  [cyan]findfeed[/cyan] <url/téma>     najít RSS feed pro web nebo téma

  [bold]AI[/bold]
  [cyan]ask[/cyan] <otázka>            zeptat se AI agenta (vyžaduje API klíč)
  [cyan]forums[/cyan] <otázka>         zeptat se na rodičovské diskuze

  [bold]Systém[/bold]
  [cyan]help[/cyan]                    tento přehled
  [cyan]quit[/cyan] / Ctrl+C          zastavit server a ukončit
"""


# ── SERVER ────────────────────────────────────────────────────────────────────

class ServerThread(threading.Thread):
    def __init__(self, host: str, port: int):
        super().__init__(daemon=True, name="feedwatch-server")
        self.host = host
        self.port = port
        self.server: uvicorn.Server | None = None

    def run(self):
        from feedwatch.api.main import app
        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self.server = uvicorn.Server(config)
        self.server.run()

    def stop(self):
        if self.server:
            self.server.should_exit = True


# ── COMMAND HANDLERS ──────────────────────────────────────────────────────────

async def cmd_refresh(db):
    from feedwatch.services.fetcher import fetch_all
    from feedwatch.services.analyzer import analyze_pending
    from feedwatch.services.embedder import embed_pending
    from feedwatch.agents.summarizer import summarize_pending
    from feedwatch.api.routes.live import broadcast

    broadcast("status", {"msg": "🔄 Fetching feeds..."})
    console.print("[dim]Fetching...[/dim] ", end="")
    fetched = await fetch_all(db)

    broadcast("status", {"msg": "😊 Analyzing..."})
    console.print("[dim]Analyzing...[/dim] ", end="")
    analyzed = await analyze_pending(db)

    broadcast("status", {"msg": "🧠 Embedding..."})
    console.print("[dim]Embedding...[/dim] ", end="")
    embedded = await embed_pending(db)

    broadcast("status", {"msg": "✍️ Summarizing..."})
    summarized = await summarize_pending(db)

    total = sum(fetched.values())
    broadcast("refresh_done", {
        "total": total, "analyzed": analyzed,
        "embedded": embedded, "summarized": summarized, "feeds": fetched,
    })
    console.print(f"\n[green]✓[/green] {total} new · {analyzed} analyzed · {embedded} embedded · {summarized} summarized")
    for name, count in fetched.items():
        if count:
            console.print(f"  [cyan]{name}:[/cyan] {count}")


async def cmd_feeds(db):
    from sqlalchemy import select, func
    from feedwatch.models.feed import Feed
    from feedwatch.models.article import Article
    from rich.table import Table
    from rich import box

    result = await db.execute(
        select(Feed, func.count(Article.id))
        .outerjoin(Article).group_by(Feed.id).order_by(Feed.name)
    )
    rows = result.all()
    if not rows:
        console.print("[dim]Žádné feedy. Přidej: add <url> <název>[/dim]")
        return

    t = Table(box=box.SIMPLE, highlight=True)
    t.add_column("ID", style="dim", width=4)
    t.add_column("Název", style="bold cyan")
    t.add_column("Kategorie", style="magenta")
    t.add_column("Články", justify="right")
    t.add_column("Naposledy", style="dim")
    for feed, count in rows:
        last = feed.last_fetched.strftime("%m-%d %H:%M") if feed.last_fetched else "nikdy"
        t.add_row(str(feed.id), feed.name, feed.category, str(count), last)
    console.print(t)


async def cmd_list(db, args):
    from sqlalchemy import select
    from feedwatch.models.article import Article
    from rich.table import Table
    from rich import box
    from rich.text import Text

    limit = int(args[0]) if args and args[0].isdigit() else 15
    result = await db.execute(
        select(Article).order_by(Article.fetched_at.desc()).limit(limit)
    )
    articles = result.scalars().all()
    if not articles:
        console.print("[dim]Žádné články. Spusť: refresh[/dim]")
        return

    STYLE = {"positive": "green", "negative": "red", "neutral": "yellow"}
    t = Table(box=box.SIMPLE, show_lines=False)
    t.add_column("Titulek", max_width=60)
    t.add_column("Sentiment", justify="center", width=12)
    t.add_column("Skóre", justify="right", width=7)
    for a in articles:
        s = STYLE.get(a.sentiment_label or "", "dim")
        t.add_row(
            a.title[:60],
            Text(a.sentiment_label or "?", style=s),
            Text(f"{a.sentiment_score:+.2f}" if a.sentiment_score else "—", style=s),
        )
    console.print(t)


async def cmd_top(db, args):
    from sqlalchemy import select
    from feedwatch.models.article import Article
    from rich.table import Table
    from rich import box

    n = int(args[0]) if args and args[0].isdigit() else 5
    result = await db.execute(
        select(Article).where(Article.sentiment_score.isnot(None))
        .order_by(Article.sentiment_score.desc()).limit(n * 4)
    )
    articles = result.scalars().all()

    pos = [a for a in articles if a.sentiment_label == "positive"][:n]
    neg = sorted([a for a in articles if a.sentiment_label == "negative"],
                 key=lambda x: x.sentiment_score)[:n]

    for items, title, color in [(pos, "Top Positive", "green"), (neg, "Top Negative", "red")]:
        if not items:
            continue
        t = Table(title=title, box=box.SIMPLE_HEAVY, border_style=color)
        t.add_column("Skóre", width=7, style=color, justify="right")
        t.add_column("Titulek", max_width=65)
        for a in items:
            t.add_row(f"{a.sentiment_score:+.2f}", a.title[:65])
        console.print(t)


async def cmd_search(args):
    if not args:
        console.print("[red]Použití: search <dotaz>[/red]")
        return
    from feedwatch.services.embedder import semantic_search
    from rich.table import Table
    from rich import box
    from rich.text import Text

    query = " ".join(args)
    results = semantic_search(query, n_results=10)
    if not results:
        console.print("[dim]Žádné výsledky.[/dim]")
        return

    STYLE = {"positive": "green", "negative": "red", "neutral": "yellow"}
    t = Table(title=f'🔍 "{query}"', box=box.SIMPLE)
    t.add_column("Skóre", width=6, justify="right")
    t.add_column("Titulek", max_width=60)
    t.add_column("Sentiment", width=10, justify="center")
    t.add_column("URL", max_width=35, style="dim")
    for r in results:
        m = r["metadata"]
        s = STYLE.get(m.get("sentiment_label", ""), "dim")
        t.add_row(
            f"{r['score']:.2f}",
            m["title"][:60],
            Text(m.get("sentiment_label", "?"), style=s),
            m.get("url", "")[:35],
        )
    console.print(t)


async def cmd_add(db, args):
    if len(args) < 2:
        console.print("[red]Použití: add <url> <název>[/red]")
        return
    from sqlalchemy import select
    from feedwatch.models.feed import Feed
    from feedwatch.api.routes.live import broadcast

    url, name = args[0], " ".join(args[1:])
    existing = (await db.execute(select(Feed).where(Feed.url == url))).scalar_one_or_none()
    if existing:
        console.print(f"[yellow]Feed již existuje:[/yellow] {url}")
        return
    feed = Feed(url=url, name=name, category="general")
    db.add(feed)
    await db.commit()
    broadcast("feed_added", {"name": name, "url": url})
    console.print(f"[green]Přidáno:[/green] [bold]{name}[/bold]")


async def cmd_stats(db):
    from sqlalchemy import select, func
    from feedwatch.models.article import Article
    from feedwatch.models.feed import Feed

    total = (await db.execute(select(func.count(Article.id)))).scalar()
    feeds = (await db.execute(select(func.count(Feed.id)))).scalar()
    sentiment = (await db.execute(
        select(Article.sentiment_label, func.count(Article.id)).group_by(Article.sentiment_label)
    )).all()
    s = {lbl or "?": cnt for lbl, cnt in sentiment}
    console.print(
        f"[cyan]Feedy:[/cyan] {feeds}  "
        f"[cyan]Články:[/cyan] {total}  "
        f"[green]Pozitivní:[/green] {s.get('positive',0)}  "
        f"[red]Negativní:[/red] {s.get('negative',0)}  "
        f"[yellow]Neutrální:[/yellow] {s.get('neutral',0)}"
    )


async def cmd_websearch(args, news: bool = False):
    if not args:
        console.print("[red]Použití: websearch <dotaz>[/red]")
        return
    from duckduckgo_search import DDGS
    from rich.table import Table
    from rich import box

    query = " ".join(args)
    console.print(f"[dim]Hledám na webu: {query}...[/dim]")

    try:
        with DDGS() as ddgs:
            if news:
                results = list(ddgs.news(query, max_results=10))
            else:
                results = list(ddgs.text(query, max_results=10))
    except Exception as e:
        console.print(f"[red]Chyba hledání:[/red] {e}")
        return

    if not results:
        console.print("[dim]Žádné výsledky.[/dim]")
        return

    t = Table(title=f'🌐 Web: "{query}"', box=box.SIMPLE, show_lines=True)
    t.add_column("#", width=3, style="dim")
    t.add_column("Titulek", max_width=55)
    t.add_column("Zdroj / URL", max_width=35, style="dim")

    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        url = r.get("url", r.get("link", ""))
        body = r.get("body", r.get("excerpt", ""))
        source = r.get("source", url.split("/")[2] if url else "")
        t.add_row(str(i), f"{title[:55]}\n[dim]{body[:80]}[/dim]" if body else title[:55], source[:35])

    console.print(t)
    console.print(f"[dim]Tip: add <url> <název> — přidej RSS feed z výsledku[/dim]")


async def cmd_findfeed(args):
    if not args:
        console.print("[red]Použití: findfeed <url nebo téma>[/red]")
        return
    from duckduckgo_search import DDGS
    import httpx
    from bs4 import BeautifulSoup
    from rich.table import Table
    from rich import box

    query = " ".join(args)
    feeds_found = []

    # pokud je to URL — zkusíme najít RSS přímo na stránce
    if query.startswith("http"):
        console.print(f"[dim]Hledám RSS na {query}...[/dim]")
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
                resp = await client.get(query)
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup.find_all("link", type=["application/rss+xml", "application/atom+xml"]):
                    href = tag.get("href", "")
                    if href:
                        if not href.startswith("http"):
                            from urllib.parse import urljoin
                            href = urljoin(query, href)
                        feeds_found.append({
                            "url": href,
                            "title": tag.get("title", href),
                            "source": query,
                        })
        except Exception as e:
            console.print(f"[yellow]Přímé hledání selhalo:[/yellow] {e}")

    # DuckDuckGo hledání RSS feedů
    if not feeds_found:
        console.print(f"[dim]Hledám RSS feedy pro: {query}...[/dim]")
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(f"{query} RSS feed site:*", max_results=8))
            for r in results:
                url = r.get("url", r.get("link", ""))
                if any(x in url for x in ["rss", "feed", "atom", ".xml"]):
                    feeds_found.append({
                        "url": url,
                        "title": r.get("title", url),
                        "source": "DDG search",
                    })
        except Exception as e:
            console.print(f"[red]Chyba:[/red] {e}")

    if not feeds_found:
        console.print("[dim]Žádné RSS feedy nenalezeny. Zkus: websearch <téma>[/dim]")
        return

    t = Table(title=f'📡 RSS feedy: "{query}"', box=box.SIMPLE)
    t.add_column("#", width=3, style="dim")
    t.add_column("Název", max_width=40)
    t.add_column("URL", max_width=50, style="cyan")
    for i, f in enumerate(feeds_found, 1):
        t.add_row(str(i), f["title"][:40], f["url"][:50])

    console.print(t)
    console.print("[dim]Přidej feed: add <url> <název>[/dim]")


async def cmd_ask(args, db):
    if not args:
        console.print("[red]Použití: ask <otázka>[/red]")
        return
    from feedwatch.config import settings
    if not settings.anthropic_api_key:
        console.print("[yellow]⚠ API klíč není nastaven.[/yellow]")
        console.print("[dim]Spusť: feedwatch start --api-key sk-ant-...[/dim]")
        return
    from feedwatch.agents.qa_agent import ask
    question = " ".join(args)
    console.print("[dim]Přemýšlím...[/dim]")
    answer = await ask(question, db)
    from rich.panel import Panel
    console.print(Panel(answer, title="[cyan]AI odpověď[/cyan]", border_style="cyan"))


async def cmd_forums(args, db):
    from feedwatch.config import settings
    if not settings.anthropic_api_key:
        console.print("[yellow]⚠ API klíč není nastaven.[/yellow]")
        return
    from feedwatch.agents.forum_agent import digest
    question = " ".join(args) if args else "Co řeší rodiče autistických dětí nejčastěji?"
    console.print("[dim]Prohledávám diskuze...[/dim]")
    answer = await digest(question, db)
    from rich.panel import Panel
    console.print(Panel(answer, title="[cyan]Diskuze rodičů[/cyan]", border_style="cyan"))


# ── REPL LOOP ─────────────────────────────────────────────────────────────────

class FeedwatchREPL:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._running = True
        self._server_thread: ServerThread | None = None

    def start_server(self):
        self._server_thread = ServerThread(self.host, self.port)
        self._server_thread.start()

    def stop(self):
        self._running = False
        if self._server_thread:
            self._server_thread.stop()

    async def _dispatch(self, line: str) -> None:
        from feedwatch.db import init_db, AsyncSessionLocal

        parts = line.strip().split()
        if not parts:
            return
        verb, args = parts[0].lower(), parts[1:]

        if verb in ("quit", "exit", "q"):
            console.print("[yellow]Zastavuji server...[/yellow]")
            self.stop()
            return

        if verb == "help":
            console.print(HELP)
            return

        # příkazy bez DB
        if verb == "search":
            await cmd_search(args)
            return
        if verb == "websearch":
            await cmd_websearch(args)
            return
        if verb == "webnews":
            await cmd_websearch(args, news=True)
            return
        if verb == "findfeed":
            await cmd_findfeed(args)
            return

        # příkazy s DB
        await init_db()
        async with AsyncSessionLocal() as db:
            if verb == "refresh":
                await cmd_refresh(db)
            elif verb == "feeds":
                await cmd_feeds(db)
            elif verb == "list":
                await cmd_list(db, args)
            elif verb == "top":
                await cmd_top(db, args)
            elif verb == "add":
                await cmd_add(db, args)
            elif verb == "stats":
                await cmd_stats(db)
            elif verb == "ask":
                await cmd_ask(args, db)
            elif verb == "forums":
                await cmd_forums(args, db)
            else:
                console.print(f"[dim]Neznámý příkaz: [bold]{verb}[/bold] — napiš [bold]help[/bold][/dim]")

    async def run(self):
        console.print(HELP)

        while self._running:
            try:
                loop = asyncio.get_event_loop()
                try:
                    line = await loop.run_in_executor(None, lambda: input("\n[feedwatch]> "))
                except EOFError:
                    break
                if not line.strip():
                    continue
                await self._dispatch(line)
            except KeyboardInterrupt:
                console.print("\n[yellow]Zastavuji...[/yellow]")
                self.stop()
                break
            except Exception as e:
                console.print(f"[red]Chyba:[/red] {e}")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

async def run_start(host: str, port: int):
    repl = FeedwatchREPL(host=host, port=port)

    console.print(Panel(
        f"[bold green]feedwatch[/bold green]\n\n"
        f"[cyan]Web:[/cyan]      http://{host}:{port}\n"
        f"[cyan]API docs:[/cyan] http://{host}:{port}/docs\n"
        f"[cyan]Live SSE:[/cyan] http://{host}:{port}/live\n\n"
        f"[dim]Server + REPL běží paralelně — prohlížeč dostává live updaty[/dim]",
        border_style="cyan",
        padding=(1, 2),
    ))

    repl.start_server()

    # počkej na start serveru
    import httpx
    for _ in range(30):
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(f"http://localhost:{port}/health", timeout=1)
                if r.status_code == 200:
                    console.print(f"[green]✓[/green] Server běží na portu {port}\n")
                    break
        except Exception:
            await asyncio.sleep(0.4)

    await repl.run()
    console.print("[dim]Konec.[/dim]")
