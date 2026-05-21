"""
Persistentní claude CLI session — spustí se jednou při startu serveru,
přijímá zprávy přes asyncio queue, vrací odpovědi.
Používá claude --resume pro zachování kontextu mezi zprávami.
"""
import asyncio
import json
import shutil
from typing import AsyncGenerator

_session_id: str | None = None
_lock = asyncio.Lock()
_claude_bin: str | None = shutil.which("claude")


async def _run_claude(prompt: str, resume_id: str | None = None) -> AsyncGenerator[str, None]:
    """Spustí claude --print a streamuje text odpovědi."""
    if not _claude_bin:
        yield "claude CLI not found."
        return

    cmd = [
        _claude_bin,
        "--print",
        "--output-format", "stream-json",
        "--verbose",
    ]
    if resume_id:
        cmd += ["--resume", resume_id]   # dva oddělené argumenty
    else:
        cmd += ["--no-session-persistence"]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    proc.stdin.write(prompt.encode())
    await proc.stdin.drain()
    proc.stdin.close()

    session_id_found = None

    # čte celý výstup najednou — bezpečnější než po chunkcích
    output = await proc.stdout.read()
    await proc.wait()

    for line in output.split(b"\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            t = obj.get("type", "")

            if t == "assistant":
                for block in obj.get("message", {}).get("content", []):
                    if block.get("type") == "text" and block.get("text"):
                        yield block["text"]

            elif t in ("result", "system"):
                sid = obj.get("session_id")
                if sid:
                    session_id_found = sid

        except Exception:
            pass

    if session_id_found:
        global _session_id
        _session_id = session_id_found


async def chat(message: str, context: str = "") -> AsyncGenerator[str, None]:
    """
    Hlavní funkce — pošle zprávu do claude CLI.
    Při první zprávě vytvoří novou session.
    Při dalších zprávách pokračuje ve stejné session (--resume).
    Serialized přes asyncio.Lock — jedna zpráva najednou.
    """
    global _session_id

    async with _lock:
        if context:
            full_prompt = f"{context}\n\nUser: {message}"
        else:
            full_prompt = message

        async for text in _run_claude(full_prompt, resume_id=_session_id):
            yield text


async def warmup():
    """
    Předehřeje claude session při startu serveru.
    Spustí claude s krátkým systémovým promptem → uloží session_id.
    Všechny následující dotazy pak použijí --resume (rychlejší, cache).
    """
    if not _claude_bin:
        return
    global _session_id
    if _session_id:
        return  # už zahřátá

    system_prompt = (
        "You are feedwatch assistant — you help users explore their RSS feeds, "
        "news articles, and autism/education community discussions. "
        "Be concise and always cite sources with URLs. "
        "Respond in the same language the user writes in. Ready."
    )
    # spustí claude, vytvoří session, uloží session_id
    async for _ in _run_claude(system_prompt):
        pass  # odpověď nepotřebujeme, jen session_id


def reset_session():
    """Resetuje session — příští zpráva začne novou konverzaci."""
    global _session_id
    _session_id = None


def has_claude() -> bool:
    return _claude_bin is not None


def session_ready() -> bool:
    """Vrátí True pokud je session předehřátá."""
    return _session_id is not None
