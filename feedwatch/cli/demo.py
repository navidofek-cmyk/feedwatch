"""
Demo mode — seeds the database with sample articles and showcases all features.
No API key or network connection required.
"""

import asyncio
from datetime import datetime, UTC, timedelta
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text
from rich.rule import Rule
from rich.syntax import Syntax

console = Console()

SAMPLE_FEEDS = [
    {"name": "Hacker News", "url": "https://hnrss.org/frontpage", "category": "tech"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "category": "tech"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "category": "tech"},
]

SAMPLE_ARTICLES = [
    {
        "title": "OpenAI releases GPT-5 with major reasoning improvements",
        "description": "OpenAI has unveiled GPT-5, claiming it surpasses human experts on most benchmarks. The model shows dramatic improvements in coding, mathematics, and scientific reasoning.",
        "url": "https://en.wikipedia.org/wiki/GPT-4",
        "sentiment_score": 0.82,
        "sentiment_label": "positive",
        "summary": "OpenAI's GPT-5 achieves expert-level performance across coding, math, and science benchmarks.",
        "feed_name": "Ars Technica",
        "hours_ago": 2,
    },
    {
        "title": "Critical vulnerability found in popular Linux kernel module",
        "description": "Security researchers have discovered a critical zero-day vulnerability affecting millions of Linux servers. The flaw allows privilege escalation and remote code execution.",
        "url": "https://en.wikipedia.org/wiki/Privilege_escalation",
        "sentiment_score": -0.74,
        "sentiment_label": "negative",
        "summary": "A zero-day Linux kernel vulnerability enables privilege escalation on millions of servers.",
        "feed_name": "Ars Technica",
        "hours_ago": 3,
    },
    {
        "title": "Python 3.14 beta released with new type system features",
        "description": "The Python core team has released 3.14 beta. Highlights include improved type inference, faster startup times, and new syntax for pattern matching on dataclasses.",
        "url": "https://docs.python.org/3/whatsnew/3.13.html",
        "sentiment_score": 0.65,
        "sentiment_label": "positive",
        "summary": "Python 3.14 beta introduces improved typing, faster startup, and enhanced pattern matching.",
        "feed_name": "Hacker News",
        "hours_ago": 5,
    },
    {
        "title": "Ask HN: What's your favorite debugging technique?",
        "description": "A thread discussing debugging techniques including print statements, debuggers, rubber duck debugging, and systematic bisection approaches used by experienced engineers.",
        "url": "https://news.ycombinator.com/",
        "sentiment_score": 0.12,
        "sentiment_label": "neutral",
        "summary": "Community discussion on debugging techniques ranging from print statements to systematic bisection.",
        "feed_name": "Hacker News",
        "hours_ago": 6,
    },
    {
        "title": "Tesla recalls 200,000 vehicles over software defect",
        "description": "Tesla issued a recall affecting 200,000 Model 3 and Model Y vehicles due to a software bug that can cause the rearview camera to fail during reverse gear engagement.",
        "url": "https://en.wikipedia.org/wiki/Tesla_Model_3",
        "sentiment_score": -0.61,
        "sentiment_label": "negative",
        "summary": "Tesla recalls 200,000 Model 3/Y vehicles due to a rearview camera software failure.",
        "feed_name": "The Verge",
        "hours_ago": 4,
    },
    {
        "title": "Anthropic raises $4B in new funding round",
        "description": "AI safety company Anthropic has secured $4 billion in fresh funding, valuing the company at $40 billion. The round was led by Google and includes participation from Spark Capital.",
        "url": "https://en.wikipedia.org/wiki/Anthropic",
        "sentiment_score": 0.77,
        "sentiment_label": "positive",
        "summary": "Anthropic raises $4B at a $40B valuation, led by Google.",
        "feed_name": "The Verge",
        "hours_ago": 8,
    },
    {
        "title": "Rust overtakes C++ in systems programming survey for first time",
        "description": "The annual Stack Overflow developer survey shows Rust has surpassed C++ in systems programming usage for the first time. Memory safety and tooling cited as main reasons.",
        "url": "https://en.wikipedia.org/wiki/Rust_(programming_language)",
        "sentiment_score": 0.54,
        "sentiment_label": "positive",
        "summary": "Rust surpasses C++ in systems programming for the first time, with memory safety as the key factor.",
        "feed_name": "Hacker News",
        "hours_ago": 10,
    },
    {
        "title": "EU fines Meta €1.3B for GDPR violations in data transfers",
        "description": "European regulators have issued the largest GDPR fine in history against Meta for illegally transferring European user data to US servers without adequate protection mechanisms.",
        "url": "https://en.wikipedia.org/wiki/General_Data_Protection_Regulation",
        "sentiment_score": -0.68,
        "sentiment_label": "negative",
        "summary": "Meta receives record €1.3B GDPR fine for illegal EU-to-US user data transfers.",
        "feed_name": "Ars Technica",
        "hours_ago": 12,
    },
    {
        "title": "Show HN: I built a local-first Notion alternative in Go",
        "description": "Developer shares their open-source, local-first note-taking app built in Go with SQLite backend. Supports markdown, tables, and offline-first sync.",
        "url": "https://github.com/usememos/memos",
        "sentiment_score": 0.43,
        "sentiment_label": "positive",
        "summary": "Open-source local-first Notion alternative built in Go with SQLite and offline-first sync.",
        "feed_name": "Hacker News",
        "hours_ago": 14,
    },
    {
        "title": "Apple Vision Pro 2 leaks suggest 40% weight reduction",
        "description": "New leaks from supply chain sources indicate the Apple Vision Pro 2 will be significantly lighter, use a new micro-OLED display, and feature improved battery life of up to 4 hours.",
        "url": "https://en.wikipedia.org/wiki/Apple_Vision_Pro",
        "sentiment_score": 0.38,
        "sentiment_label": "positive",
        "summary": "Apple Vision Pro 2 leaks point to 40% weight reduction, new micro-OLED, and 4-hour battery.",
        "feed_name": "The Verge",
        "hours_ago": 18,
    },
]


async def seed_database() -> None:
    from feedwatch.db import init_db, AsyncSessionLocal
    from feedwatch.models.feed import Feed
    from feedwatch.models.article import Article
    from sqlalchemy import select

    await init_db()

    async with AsyncSessionLocal() as db:
        # feeds
        feed_map: dict[str, Feed] = {}
        for f in SAMPLE_FEEDS:
            existing = (await db.execute(select(Feed).where(Feed.url == f["url"]))).scalar_one_or_none()
            if not existing:
                feed = Feed(url=f["url"], name=f["name"], category=f["category"])
                db.add(feed)
                await db.flush()
                feed_map[f["name"]] = feed
            else:
                feed_map[f["name"]] = existing

        await db.flush()

        # articles
        added = 0
        for a in SAMPLE_ARTICLES:
            guid = a["url"]
            existing = (await db.execute(select(Article).where(Article.guid == guid))).scalar_one_or_none()
            if existing:
                continue

            feed = feed_map[a["feed_name"]]
            published = datetime.now(UTC) - timedelta(hours=a["hours_ago"])
            article = Article(
                feed_id=feed.id,
                guid=guid,
                title=a["title"],
                description=a["description"],
                url=a["url"],
                published_at=published,
                sentiment_score=a["sentiment_score"],
                sentiment_label=a["sentiment_label"],
                summary=a["summary"],
                embedded=True,
            )
            db.add(article)
            added += 1

        await db.commit()
        return added


def _sentiment_badge(label: str | None, score: float | None) -> Text:
    icons = {"positive": "▲", "negative": "▼", "neutral": "●"}
    styles = {"positive": "bold green", "negative": "bold red", "neutral": "bold yellow"}
    icon = icons.get(label or "", "?")
    style = styles.get(label or "", "dim")
    score_str = f"{score:+.2f}" if score is not None else ""
    return Text(f"{icon} {score_str}", style=style)


def run_demo() -> None:
    console.print()
    console.print(Panel(
        "[bold white]feedwatch[/bold white] [dim]— RSS aggregator with AI agents[/dim]\n"
        "[dim]Demo mode · sample data · no API key required[/dim]",
        border_style="bright_blue",
        padding=(1, 4),
    ))

    # 1. seed
    console.print()
    console.print(Rule("[dim]seeding database[/dim]"))
    added = asyncio.run(seed_database())
    console.print(f"  [green]✓[/green] {len(SAMPLE_FEEDS)} feeds, {added} new articles loaded\n")

    # 2. feeds table
    console.print(Rule("[dim]feedwatch feeds[/dim]"))
    console.print()
    t = Table(box=box.ROUNDED, highlight=True, border_style="bright_blue")
    t.add_column("ID", style="dim", width=4)
    t.add_column("Name", style="bold cyan")
    t.add_column("Category", style="magenta")
    t.add_column("Articles", justify="right")
    t.add_column("Active", justify="center")
    for i, f in enumerate(SAMPLE_FEEDS, 1):
        count = sum(1 for a in SAMPLE_ARTICLES if a["feed_name"] == f["name"])
        t.add_row(str(i), f["name"], f["category"], str(count), "[green]✓[/green]")
    console.print(t)

    # 3. articles
    console.print()
    console.print(Rule("[dim]feedwatch list --hours 24[/dim]"))
    console.print()
    t2 = Table(box=box.ROUNDED, show_lines=True, border_style="bright_blue")
    t2.add_column("Title", max_width=48)
    t2.add_column("Feed", style="dim", width=14)
    t2.add_column("Sentiment", justify="center", width=12)
    t2.add_column("Summary", max_width=38, style="dim")
    for a in SAMPLE_ARTICLES[:7]:
        t2.add_row(
            a["title"][:48],
            a["feed_name"],
            _sentiment_badge(a["sentiment_label"], a["sentiment_score"]),
            a["summary"][:38],
        )
    console.print(t2)

    # 4. top
    console.print()
    console.print(Rule("[dim]feedwatch top --hours 24[/dim]"))
    console.print()

    positives = sorted([a for a in SAMPLE_ARTICLES if a["sentiment_label"] == "positive"],
                       key=lambda x: -x["sentiment_score"])[:3]
    negatives = sorted([a for a in SAMPLE_ARTICLES if a["sentiment_label"] == "negative"],
                       key=lambda x: x["sentiment_score"])[:3]

    tp = Table(title="Top Positive", box=box.SIMPLE_HEAVY, border_style="green")
    tp.add_column("Score", width=7, justify="right", style="green")
    tp.add_column("Title", max_width=55)
    for a in positives:
        tp.add_row(f"{a['sentiment_score']:+.2f}", a["title"])
    console.print(tp)

    tn = Table(title="Top Negative", box=box.SIMPLE_HEAVY, border_style="red")
    tn.add_column("Score", width=7, justify="right", style="red")
    tn.add_column("Title", max_width=55)
    for a in negatives:
        tn.add_row(f"{a['sentiment_score']:+.2f}", a["title"])
    console.print(tn)

    # 5. search
    console.print()
    console.print(Rule('[dim]feedwatch search "AI funding"[/dim]'))
    console.print()
    relevant = [a for a in SAMPLE_ARTICLES if any(
        kw in a["title"].lower() or kw in a["description"].lower()
        for kw in ["ai", "openai", "anthropic", "funding", "model"]
    )][:4]
    ts = Table(box=box.ROUNDED, border_style="bright_blue")
    ts.add_column("Score", width=7, justify="right", style="cyan")
    ts.add_column("Title", max_width=50)
    ts.add_column("Sentiment", justify="center", width=12)
    for i, a in enumerate(relevant):
        score = round(0.97 - i * 0.08, 2)
        ts.add_row(f"{score:.2f}", a["title"][:50], _sentiment_badge(a["sentiment_label"], a["sentiment_score"]))
    console.print(ts)

    # 6. ask (simulated)
    console.print()
    console.print(Rule('[dim]feedwatch ask "What are the biggest AI stories today?"[/dim]'))
    console.print()
    ai_answer = (
        "Based on your feeds, here are the biggest AI stories:\n\n"
        "1. [bold]OpenAI releases GPT-5[/bold] [green](+0.82)[/green]\n"
        "   Major reasoning improvements, surpasses human experts on benchmarks.\n"
        "   [dim]→ https://example.com/gpt5[/dim]\n\n"
        "2. [bold]Anthropic raises $4B in new funding[/bold] [green](+0.77)[/green]\n"
        "   Valued at $40B, round led by Google.\n"
        "   [dim]→ https://example.com/anthropic-funding[/dim]\n\n"
        "[dim]Overall AI sentiment today: [green]positive[/green] (avg +0.79)[/dim]"
    )
    console.print(Panel(
        ai_answer,
        title="[bold cyan]AI Answer[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))

    # 7. CLI reference
    console.print()
    console.print(Rule("[dim]available commands[/dim]"))
    console.print()
    commands = [
        ("feedwatch add <url> --name <n>", "add a new RSS feed"),
        ("feedwatch feeds", "list all feeds"),
        ("feedwatch refresh", "fetch + analyze + embed + summarize"),
        ("feedwatch list --hours 6 --sentiment positive", "browse articles"),
        ("feedwatch top --hours 24", "top positive / negative"),
        ("feedwatch search <query>", "semantic vector search"),
        ("feedwatch ask <question>", "ask the AI agent"),
        ("feedwatch serve", "start REST API server"),
    ]
    tc = Table(box=box.SIMPLE, show_header=False)
    tc.add_column("Command", style="bold cyan", min_width=46)
    tc.add_column("Description", style="dim")
    for cmd, desc in commands:
        tc.add_row(cmd, desc)
    console.print(tc)

    console.print()
    console.print(Panel(
        "[dim]To use the AI features, add your key to [bold].env[/bold]:[/dim]\n"
        "[green]ANTHROPIC_API_KEY=sk-ant-...[/green]",
        border_style="dim",
        padding=(0, 2),
    ))
    console.print()
