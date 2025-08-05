import os
import sys
import re
import json
import time
import asyncio
import logging

import aiohttp
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

# ─── Persistence Setup ────────────────────────────────────────────
STORAGE_FILE = os.path.join(os.getcwd(), "fragment_saves.json")
try:
    with open(STORAGE_FILE, encoding="utf-8") as f:
        raw = json.load(f)
        _saves: dict[int, list[str]] = {int(k): v for k, v in raw.items()}
except (FileNotFoundError, json.JSONDecodeError):
    _saves = {}

def _persist():
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(_saves, f, ensure_ascii=False)

# ─── TTL Cache Setup ──────────────────────────────────────────────
CACHE_TTL = 3600  # seconds
_cache: dict[str, tuple[float, bool|None]] = {}  # phone → (timestamp, restricted?)

def _get_cached(number: str):
    entry = _cache.get(number)
    if entry and time.time() - entry[0] < CACHE_TTL:
        return entry[1]
    return None

def _set_cache(number: str, restricted: bool|None):
    _cache[number] = (time.time(), restricted)

# ─── Boilerplate & Globals ────────────────────────────────────────
logger = logging.getLogger(__name__)
MAX_SAVE = 400
DEFAULT_HEADERS = {
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

# grab dispatcher from main
_main = sys.modules.get("__main__")
dp = getattr(_main, "dp", None)

def _user_id(msg: Message) -> int:
    return msg.from_user.id

def _canonical(num: str) -> str:
    # strip everything but digits
    return re.sub(r"\D", "", num)

# ─── /save ─────────────────────────────────────────────────────────
@dp.message(Command("save"))
async def save_numbers(message: Message):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply(
            "⚠️ Usage: `/save <num1> [num2 …]`", parse_mode="Markdown"
        )

    tokens = re.split(r"[,\|\n]+", parts[1])
    user = _user_id(message)
    current = _saves.setdefault(user, [])
    added = 0

    for tok in tokens:
        num = _canonical(tok)
        if num and len(current) < MAX_SAVE and num not in current:
            current.append(num)
            added += 1

    # dedupe and persist
    _saves[user] = list(dict.fromkeys(current))
    _persist()

    await message.reply(
        f"✅ Added {added} number{'s' if added != 1 else ''}. "
        f"Total stored: {len(_saves[user])}/{MAX_SAVE}."
    )

# ─── /clear & /clearall ───────────────────────────────────────────
@dp.message(Command(commands=["clear", "clearall"]))
async def clear_numbers(message: Message):
    user = _user_id(message)
    if user in _saves:
        _saves.pop(user)
        _persist()
    await message.reply("🗑️ All your saved numbers have been cleared.")

# ─── /checkall ────────────────────────────────────────────────────
@dp.message(Command("checkall"))
async def check_all(message: Message):
    user = _user_id(message)
    nums = _saves.get(user, [])
    if not nums:
        return await message.reply("📭 No numbers saved. Use `/save` first.")

    # ensure normalized & deduped
    nums = sorted(set(_canonical(n) for n in nums))
    status = await message.reply(f"⏳ Checking {len(nums)} numbers…")

    sem     = asyncio.Semaphore(min(len(nums), 100))
    timeout = aiohttp.ClientTimeout(total=8)
    conn    = aiohttp.TCPConnector(limit_per_host=100)

    async def fetch(number: str, session: aiohttp.ClientSession):
        # consult cache first
        cached = _get_cached(number)
        if cached is not None:
            return number, cached

        url = f"https://fragment.com/phone/{number}"
        try:
            async with sem, session.get(url, timeout=timeout) as resp:
                text = await resp.text()
                restricted = "This phone number is restricted on Telegram" in text
        except Exception as e:
            logger.warning(f"Fetch failed for {number}: {e}")
            restricted = None

        _set_cache(number, restricted)
        return number, restricted

    async with aiohttp.ClientSession(connector=conn, headers=DEFAULT_HEADERS) as session:
        tasks = [fetch(n, session) for n in nums]
        results = await asyncio.gather(*tasks)

    # separate results
    restricted = [n for n, ok in results if ok]
    unknown    = [n for n, ok in results if ok is None]

    # reply numbered restricted
    if restricted:
        await message.reply(f"🔒 Restricted: {len(restricted)}/{len(nums)}")
        for idx, n in enumerate(sorted(restricted), start=1):
            await message.reply(
                f"{idx}. <a href='https://fragment.com/phone/{n}'>{n}</a>",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
    else:
        await message.reply(f"✅ No restricted numbers out of {len(nums)} checked.")

    # report any that couldn’t be verified
    if unknown:
        await message.reply("⚠️ Could not verify:\n" + "\n".join(unknown))

    await status.delete()

# ─── Inline /check ─────────────────────────────────────────────────
@dp.inline_query()
async def inline_check(inline_query):
    user = inline_query.from_user.id
    nums = _saves.get(user, [])
    if not nums:
        content = "📭 No numbers saved. Use `/save` first."
    else:
        # same fetch logic as above
        nums = sorted(set(_canonical(n) for n in nums))
        sem     = asyncio.Semaphore(min(len(nums), 100))
        timeout = aiohttp.ClientTimeout(total=5)
        conn    = aiohttp.TCPConnector(limit_per_host=100)

        async def fetch(number, session):
            cached = _get_cached(number)
            if cached is not None:
                return number, cached
            try:
                async with sem, session.get(f"https://fragment.com/phone/{number}", timeout=timeout) as resp:
                    text = await resp.text()
                    restricted = "This phone number is restricted on Telegram" in text
            except:
                restricted = None
            _set_cache(number, restricted)
            return number, restricted

        async with aiohttp.ClientSession(connector=conn, headers=DEFAULT_HEADERS) as session:
            results = await asyncio.gather(*(fetch(n, session) for n in nums))

        restricted = sorted(n for n, ok in results if ok)
        if restricted:
            content = "\n".join(
                f"🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>"
                for n in restricted
            )
        else:
            content = "✅ No restricted numbers found."

    article = InlineQueryResultArticle(
        id="restricted",
        title="Restricted Numbers",
        input_message_content=InputTextMessageContent(content),
    )
    await inline_query.answer([article], cache_time=0)
