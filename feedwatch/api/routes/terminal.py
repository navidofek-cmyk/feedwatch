"""
WebSocket terminál — příkazy z prohlížeče se spustí na serveru.
Výsledky se streamují zpět jako ANSI text.
"""
import asyncio
import io
from contextlib import redirect_stdout, redirect_stderr

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from rich.console import Console

router = APIRouter(tags=["terminal"])


async def _exec_command(line: str) -> str:
    """Spustí REPL příkaz a vrátí výstup jako string."""
    from feedwatch.cli.repl import (
        cmd_refresh, cmd_feeds, cmd_list, cmd_top,
        cmd_search, cmd_add, cmd_stats,
        cmd_websearch, cmd_findfeed, cmd_ask, cmd_forums,
    )
    from feedwatch.db import init_db, AsyncSessionLocal

    buf = io.StringIO()
    con = Console(file=buf, highlight=False, markup=True, width=90)

    parts = line.strip().split()
    if not parts:
        return ""
    verb, args = parts[0].lower(), parts[1:]

    try:
        if verb in ("help", "?"):
            con.print("""[bold cyan]Příkazy:[/bold cyan]
  [cyan]refresh[/cyan]              stáhnout nové články
  [cyan]feeds[/cyan]                seznam feedů
  [cyan]list[/cyan] [n]             poslední články
  [cyan]top[/cyan] [n]              nejlepší/nejhorší
  [cyan]search[/cyan] <dotaz>       sémantické hledání v DB
  [cyan]websearch[/cyan] <dotaz>    hledat na webu (DuckDuckGo)
  [cyan]webnews[/cyan] <dotaz>      hledat novinky na webu
  [cyan]findfeed[/cyan] <url/téma>  najít RSS feed
  [cyan]add[/cyan] <url> <název>    přidat feed
  [cyan]stats[/cyan]                statistiky
  [cyan]ask[/cyan] <otázka>         AI agent (vyžaduje API klíč)""")

        elif verb == "search":
            await cmd_search(args)  # uses global console — override
            # redo with local console
            if args:
                from feedwatch.services.embedder import semantic_search
                from rich.table import Table
                from rich import box
                from rich.text import Text
                query = " ".join(args)
                results = semantic_search(query, n_results=8)
                if not results:
                    con.print("[dim]Žádné výsledky.[/dim]")
                else:
                    STYLE = {"positive": "green", "negative": "red", "neutral": "yellow"}
                    t = Table(title=f'🔍 "{query}"', box=box.SIMPLE)
                    t.add_column("Skóre", width=6, justify="right")
                    t.add_column("Titulek", max_width=55)
                    t.add_column("Sentiment", width=10, justify="center")
                    for r in results:
                        m = r["metadata"]
                        s = STYLE.get(m.get("sentiment_label", ""), "dim")
                        t.add_row(f"{r['score']:.2f}", m["title"][:55], Text(m.get("sentiment_label","?"), style=s))
                    con.print(t)

        elif verb == "websearch":
            if not args:
                con.print("[red]Použití: websearch <dotaz>[/red]")
            else:
                from duckduckgo_search import DDGS
                from rich.table import Table
                from rich import box
                query = " ".join(args)
                con.print(f"[dim]Hledám: {query}...[/dim]")
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=8))
                t = Table(title=f'🌐 "{query}"', box=box.SIMPLE, show_lines=True)
                t.add_column("#", width=3, style="dim")
                t.add_column("Titulek", max_width=50)
                t.add_column("Zdroj", max_width=28, style="dim")
                for i, r in enumerate(results, 1):
                    title = r.get("title", "")
                    url = r.get("url", r.get("link", ""))
                    body = r.get("body", "")
                    src = url.split("/")[2] if url else ""
                    cell = f"{title[:50]}\n[dim]{body[:70]}[/dim]" if body else title[:50]
                    t.add_row(str(i), cell, src[:28])
                con.print(t)
                con.print("[dim]add <url> <název> — přidej jako feed[/dim]")

        elif verb == "webnews":
            if not args:
                con.print("[red]Použití: webnews <dotaz>[/red]")
            else:
                from duckduckgo_search import DDGS
                from rich.table import Table
                from rich import box
                query = " ".join(args)
                con.print(f"[dim]Hledám novinky: {query}...[/dim]")
                with DDGS() as ddgs:
                    results = list(ddgs.news(query, max_results=8))
                t = Table(title=f'📰 Novinky: "{query}"', box=box.SIMPLE, show_lines=True)
                t.add_column("#", width=3, style="dim")
                t.add_column("Titulek", max_width=50)
                t.add_column("Zdroj", max_width=25, style="dim")
                for i, r in enumerate(results, 1):
                    t.add_row(str(i), r.get("title","")[:50], r.get("source","")[:25])
                con.print(t)

        elif verb == "findfeed":
            if not args:
                con.print("[red]Použití: findfeed <url nebo téma>[/red]")
            else:
                query = " ".join(args)
                con.print(f"[dim]Hledám RSS feedy pro: {query}...[/dim]")
                from duckduckgo_search import DDGS
                from rich.table import Table
                from rich import box
                feeds_found = []
                if query.startswith("http"):
                    import httpx
                    from bs4 import BeautifulSoup
                    from urllib.parse import urljoin
                    try:
                        async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
                            resp = await client.get(query)
                            soup = BeautifulSoup(resp.text, "html.parser")
                            for tag in soup.find_all("link", type=["application/rss+xml","application/atom+xml"]):
                                href = tag.get("href","")
                                if href:
                                    if not href.startswith("http"):
                                        href = urljoin(query, href)
                                    feeds_found.append({"url": href, "title": tag.get("title", href)})
                    except Exception:
                        pass
                if not feeds_found:
                    with DDGS() as ddgs:
                        results = list(ddgs.text(f"{query} RSS feed", max_results=8))
                    for r in results:
                        url = r.get("url", r.get("link",""))
                        if any(x in url for x in ["rss","feed","atom",".xml"]):
                            feeds_found.append({"url": url, "title": r.get("title", url)})
                if not feeds_found:
                    con.print("[dim]Nenalezeny žádné RSS feedy.[/dim]")
                else:
                    t = Table(title=f'📡 RSS: "{query}"', box=box.SIMPLE)
                    t.add_column("#", width=3, style="dim")
                    t.add_column("Název", max_width=40)
                    t.add_column("URL", max_width=50, style="cyan")
                    for i, f in enumerate(feeds_found, 1):
                        t.add_row(str(i), f["title"][:40], f["url"][:50])
                    con.print(t)
                    con.print("[dim]add <url> <název>[/dim]")

        elif verb in ("refresh", "feeds", "list", "top", "add", "stats", "ask", "forums"):
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
            # cmd_* used global console — capture separately below

        else:
            con.print(f"[dim]Neznámý příkaz: [bold]{verb}[/bold] — napiš [bold]help[/bold][/dim]")

    except Exception as e:
        con.print(f"[red]Chyba:[/red] {e}")

    return buf.getvalue()


@router.websocket("/ws/terminal")
async def terminal_ws(ws: WebSocket):
    await ws.accept()
    await ws.send_text("🟢 feedwatch terminal — napiš [help] pro příkazy\n")
    try:
        while True:
            line = await ws.receive_text()
            line = line.strip()
            if not line:
                continue
            if line in ("quit", "exit"):
                await ws.send_text("[yellow]Hint: quit ukončuje pouze REPL v terminálu, ne server.[/yellow]\n")
                continue
            output = await _exec_command(line)
            if output:
                await ws.send_text(output)
            else:
                await ws.send_text("[dim]✓[/dim]\n")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
