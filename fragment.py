# fragment.py
import sys
import os
import re
import json
import asyncio
import logging
from typing import List, Dict, Tuple, Optional

import aiohttp
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

# ─── Grab dispatcher from main bot.py (aiogram v3) ─────────────────────────────
_main = sys.modules["__main__"]
dp = getattr(_main, "dp")

logger = logging.getLogger(__name__)

# ─── Persistence setup ─────────────────────────────────────────────────────────
_SAVES_FILE = os.path.join(os.getcwd(), "saves.json")
_saves: Dict[int, List[str]] = {}  # user_id → list of canonical numbers
_MAX_SAVE = 1000  # raised to 1000

def load_saves() -> None:
    global _saves
    if os.path.isfile(_SAVES_FILE):
        try:
            with open(_SAVES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _saves = {int(k): list(map(str, v)) for k, v in data.items()}
        except Exception as e:
            logger.warning(f"Failed to load saves.json: {e}")
            _saves = {}

def save_saves() -> None:
    try:
        with open(_SAVES_FILE, "w", encoding="utf-8") as f:
            json.dump(_saves, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to write saves.json: {e}")

# load at import time
load_saves()

# ─── HTTP client defaults ──────────────────────────────────────────────────────
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Heuristics to detect "restricted" on fragment page
_RESTRICT_PATTERNS = [
    re.compile(r"\brestricted on Telegram\b", re.I),
    re.compile(r"\bThis phone number is restricted\b", re.I),
    re.compile(r"\bBlocked\b", re.I),
]

# ─── Helpers ───────────────────────────────────────────────────────────────────
def _canonical(tok: str) -> str:
    """Keep digits only."""
    return re.sub(r"\D", "", (tok or ""))

def _user_id(msg: Message) -> int:
    return msg.from_user.id  # type: ignore[return-value]

def _is_restricted_html(html: str) -> Optional[bool]:
    """Return True if restricted, False if confidently not, None if unknown/error."""
    if not html:
        return None
    for p in _RESTRICT_PATTERNS:
        if p.search(html):
            return True
    # If page is reachable but no restricted markers found, treat as not restricted
    return False

async def _fetch_status(
    session: aiohttp.ClientSession,
    num: str,
    sem: asyncio.Semaphore,
    timeout_total: float,
) -> Tuple[str, Optional[bool]]:
    """
    Returns (num, restricted):
      True  → restricted
      False → not restricted
      None  → error / unknown
    """
    url = f"https://fragment.com/phone/{num}"
    try:
        async with sem:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout_total)) as resp:
                text = await resp.text(errors="ignore")
                res = _is_restricted_html(text)
                return num, res
    except Exception as e:
        logger.warning(f"Fetch failed for {num}: {e!r}")
        return num, None

def _chunk_sendable(lines: List[str], chunk_size: int = 30) -> List[str]:
    return ["\n".join(lines[i : i + chunk_size]) for i in range(0, len(lines), chunk_size)]

# ─── /save handler ─────────────────────────────────────────────────────────────
@dp.message(Command("save"))
async def save_numbers(message: Message):
    parts = message.text.strip().split(maxsplit=1) if message.text else []
    if len(parts) < 2:
        return await message.reply("⚠️ Usage: `/save <num1>[,| ]<num2> …`", parse_mode="Markdown")

    raw = re.split(r"[,\s]+", parts[1])
    uid = _user_id(message)
    store = _saves.setdefault(uid, [])
    added = 0

    for tok in raw:
        num = _canonical(tok)
        if not num:
            continue
        if len(store) >= _MAX_SAVE:
            break
        if num not in store:
            store.append(num)
            added += 1

    save_saves()
    await message.reply(f"✅ Added {added} number(s). Total stored: {len(store)}/{_MAX_SAVE}.")

# ─── /clearall handler ─────────────────────────────────────────────────────────
@dp.message(Command("clearall"))
async def clear_numbers(message: Message):
    uid = _user_id(message)
    if uid in _saves:
        _saves.pop(uid, None)
        save_saves()
    await message.reply("🗑️ All your saved numbers have been cleared.")

# ─── /checkall handler (ONLY restricted + unknown) ─────────────────────────────
@dp.message(Command("checkall"))
async def check_all(message: Message):
    uid = _user_id(message)
    nums = _saves.get(uid, [])
    if not nums:
        return await message.reply("📭 No numbers saved. Use `/save` first.", parse_mode="Markdown")

    # normalize, dedupe, sort
    nums = sorted(set(_canonical(n) for n in nums if _canonical(n)))
    status_msg = await message.reply(f"⏳ Checking {len(nums)} numbers…")

    concurrency = min(len(nums), 80)
    sem = asyncio.Semaphore(concurrency)
    timeout_total = 8.0
    conn = aiohttp.TCPConnector(limit_per_host=concurrency, ssl=False)

    async with aiohttp.ClientSession(connector=conn, headers=_DEFAULT_HEADERS) as sess:
        results = await asyncio.gather(
            *(_fetch_status(sess, n, sem, timeout_total) for n in nums),
            return_exceptions=False,
        )

    try:
        await status_msg.delete()
    except Exception:
        pass

    # Partition (no "free" reporting)
    restricted = [n for n, ok in results if ok is True]
    unknown = [n for n, ok in results if ok is None]

    total = len(nums)

    # Summary without free
    await message.reply(
        f"📊 Done.\n"
        f"🔒 Restricted: {len(restricted)}/{total}\n"
        f"⚠️ Unknown: {len(unknown)}",
        disable_web_page_preview=True,
    )

    # Send restricted list (numbered + links)
    if restricted:
        header = f"🔒 Restricted: {len(restricted)}/{total}\n"
        lines = [
            f"{i}. 🔒 <a href='https://fragment.com/phone/{num}'>{num}</a>"
            for i, num in enumerate(restricted, start=1)
        ]
        for i, chunk in enumerate(_chunk_sendable(lines, 30)):
            await message.reply(
                (header if i == 0 else "") + chunk,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
    else:
        await message.reply(f"✅ No restricted numbers found out of {total} checked.")

    # Report unknowns
    if unknown:
        unk_lines = "\n".join(unknown[:100])
        more = "" if len(unknown) <= 100 else f"\n…and {len(unknown) - 100} more."
        await message.reply("⚠️ Could not verify:\n" + unk_lines + more)

# ─── Inline @bot query (ONLY restricted + unknown) ─────────────────────────────
@dp.inline_query()
async def inline_check(inline_q: InlineQuery):
    uid = inline_q.from_user.id
    nums = _saves.get(uid, [])

    if not nums:
        article = InlineQueryResultArticle(
            id="no_saved",
            title="📭 No saved numbers",
            input_message_content=InputTextMessageContent(
                "📭 No numbers saved. Use `/save` first.", parse_mode="HTML"
            ),
            description="Use /save to add numbers",
        )
        return await inline_q.answer([article], cache_time=0, is_personal=True)

    nums = sorted(set(_canonical(n) for n in nums if _canonical(n)))

    concurrency = min(len(nums), 50)
    sem = asyncio.Semaphore(concurrency)
    timeout_total = 5.0
    conn = aiohttp.TCPConnector(limit_per_host=concurrency, ssl=False)

    async with aiohttp.ClientSession(connector=conn, headers=_DEFAULT_HEADERS) as sess:
        results = await asyncio.gather(
            *(_fetch_status(sess, n, sem, timeout_total) for n in nums),
            return_exceptions=False,
        )

    restricted = [n for n, ok in results if ok is True]
    unknown = [n for n, ok in results if ok is None]

    if restricted:
        body = "\n".join(
            f"🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>"
            for n in restricted[:400]  # keep inline message within limits
        )
    else:
        body = "✅ No restricted numbers found."

    if unknown:
        body += "\n\n⚠️ Could not verify (sample):\n" + "\n".join(unknown[:20])
        if len(unknown) > 20:
            body += f"\n…(+{len(unknown) - 20} more)"

    title = f"🔍 Restricted: {len(restricted)} | ⚠️ Unknown: {len(unknown)}"

    article = InlineQueryResultArticle(
        id="restricted_only",
        title=title,
        input_message_content=InputTextMessageContent(body, parse_mode="HTML"),
        description="Show only restricted numbers (and unknown if any)",
    )
    await inline_q.answer([article], cache_time=0, is_personal=True)
