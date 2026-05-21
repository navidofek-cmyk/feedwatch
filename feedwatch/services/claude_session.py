"""
Claude CLI session — volá claude --print pro každou zprávu.
Historie konverzace se předává jako text v promptu.
"""
import asyncio
import json
import shutil
from typing import AsyncGenerator

_claude_bin: str | None = shutil.which("claude")
_lock = asyncio.Lock()
_is_ready: bool = False


async def _call_claude(prompt: str) -> AsyncGenerator[str, None]:
    """Spustí claude --print a vrátí text odpovědi."""
    if not _claude_bin:
        yield "claude CLI not found."
        return

    cmd = [
        _claude_bin,
        "--print",
        "--output-format", "stream-json",
        "--verbose",
        "--no-session-persistence",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    proc.stdin.write(prompt.encode())
    await proc.stdin.drain()
    proc.stdin.close()

    output = await proc.stdout.read()
    await proc.wait()

    for line in output.split(b"\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if obj.get("type") == "assistant":
                for block in obj.get("message", {}).get("content", []):
                    if block.get("type") == "text" and block.get("text"):
                        yield block["text"]
        except Exception:
            pass


async def chat(message: str, context: str = "", history: list[dict] | None = None) -> AsyncGenerator[str, None]:
    """
    Pošle zprávu do claude CLI.
    Historie a kontext jsou součástí promptu.
    """
    async with _lock:
        parts = []

        # systémový kontext
        parts.append(
            "You are feedwatch news assistant. "
            "Answer based on the provided database context. "
            "Be concise. Cite sources with URLs. "
            "Respond in the same language the user writes in.\n"
        )

        # feedwatch DB kontext
        if context:
            parts.append(context)

        # historie konverzace (posledních 4 výměn)
        if history:
            parts.append("\nConversation history:")
            for msg in history[-8:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                content = str(msg.get("content", ""))[:500]
                parts.append(f"{role}: {content}")

        # aktuální zpráva
        parts.append(f"\nUser: {message}")
        parts.append("\nAssistant:")

        full_prompt = "\n".join(parts)

        async for text in _call_claude(full_prompt):
            yield text


async def warmup():
    """Předehřeje claude — spustí krátký test dotaz."""
    global _is_ready
    async for _ in _call_claude("Reply with just: ready"):
        pass
    _is_ready = True


def reset_session():
    global _is_ready
    _is_ready = False


def has_claude() -> bool:
    return _claude_bin is not None


def session_ready() -> bool:
    return _is_ready
