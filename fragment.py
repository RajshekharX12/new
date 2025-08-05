# fragment.py
import sys
import re
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

# grab dispatcher & bot from main
_main = sys.modules.get("__main__")
dp    = getattr(_main, "dp", None)

logger = logging.getLogger(__name__)

# ─── in‐memory storage per user ────────────────────────────────────
_saves: dict[int, list[str]] = {}       # user_id → list of raw tokens
_MAX_SAVE = 400

# ─── simple in‐memory cache for fetch results ──────────────────────
# number → True|False|None
_cache: dict[str, bool | None] = {}

# ─── user‐agent to pretend a real browser ───────────────────────────
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}


def _user_id(msg: Message) -> int:
    return msg.from_user.id


def _canonical(tok: str) -> str:
    # strip all non-digits
    return re.sub(r"\D", "", tok)


def _get_cached(num: str) -> bool | None:
    return _cache.get(num)


def _set_cache(num: str, val: bool | None):
    _cache[num] = val


@dp.message(Command("save"))
async def save_numbers(message: Message):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("⚠️ Usage: `/save <num1>[,| ]<num2>…`", parse_mode="Markdown")

    raw_tokens = re.split(r"[,\|\s]+", parts[1])
    uid        = _user_id(message)
    store      = _saves.setdefault(uid, [])
    added      = 0

    for tok in raw_tokens:
        num = _canonical(tok)
        if num and len(store) < _MAX_SAVE and num not in store:
            store.append(num)
            added += 1

    await message.reply(
        f"✅ Added {added} number{'s' if added != 1 else ''}. "
        f"Total stored: {len(store)}/{_MAX_SAVE}."
    )


@dp.message(Command(commands=["clear", "clearall"]))
async def clear_numbers(message: Message):
    uid = _user_id(message)
    _saves.pop(uid, None)
    await message.reply("🗑️ All your saved numbers have been cleared.")


@dp.message(Command("checkall"))
async def check_all(message: Message):
    uid  = _user_id(message)
    nums = _saves.get(uid, [])
    if not nums:
        return await message.reply("📭 No numbers saved. Use `/save` first.", parse_mode="Markdown")

    # normalize, dedupe, sort
    nums = sorted(set(_canonical(n) for n in nums))
    status = await message.reply(f"⏳ Checking {len(nums)} numbers…")

    sem     = asyncio.Semaphore(min(len(nums), 100))
    timeout = aiohttp.ClientTimeout(total=8)
    conn    = aiohttp.TCPConnector(limit_per_host=100)

    async def fetch(num: str, session: aiohttp.ClientSession):
        # check cache
        cached = _get_cached(num)
        if cached is not None:
            return num, cached

        url = f"https://fragment.com/phone/{num}"
        try:
            async with sem, session.get(url, timeout=timeout) as resp:
                html = await resp.text()
                restricted = "This phone number is restricted on Telegram" in html
        except Exception as e:
            logger.warning(f"Fetch failed for {num}: {e}")
            restricted = None

        _set_cache(num, restricted)
        return num, restricted

    async with aiohttp.ClientSession(connector=conn, headers=_DEFAULT_HEADERS) as sess:
        results = await asyncio.gather(*(fetch(n, sess) for n in nums))

    # done checking
    await status.delete()

    # filter results
    restricted = [n for n, ok in results if ok]
    unknown    = [n for n, ok in results if ok is None]

    # 1) send restricted, numbered globally, 30 lines per message
    if restricted:
        header = f"🔒 Restricted: {len(restricted)}/{len(nums)}\n"
        lines = [
            f"{i}. 🔒 <a href='https://fragment.com/phone/{num}'>{num}</a>"
            for i, num in enumerate(restricted, start=1)
        ]
        for i in range(0, len(lines), 30):
            chunk = "\n".join(lines[i:i+30])
            await message.reply(header + chunk,
                                parse_mode="HTML",
                                disable_web_page_preview=True)
            header = ""  # only show header on first chunk
    else:
        await message.reply(f"✅ No restricted numbers out of {len(nums)} checked.")

    # 2) report unknowns
    if unknown:
        await message.reply("⚠️ Could not verify:\n" + "\n".join(unknown))


@dp.inline_query()
async def inline_check(inline_query: InlineQuery):
    uid  = inline_query.from_user.id
    nums = _saves.get(uid, [])
    if not nums:
        content = "📭 No numbers saved. Use `/save` first."
    else:
        # same logic as above, but inline
        sem     = asyncio.Semaphore(min(len(nums), 100))
        timeout = aiohttp.ClientTimeout(total=5)
        conn    = aiohttp.TCPConnector(limit_per_host=100)

        async def fetch(num: str, session: aiohttp.ClientSession):
            cached = _get_cached(num)
            if cached is not None:
                return num, cached
            url = f"https://fragment.com/phone/{num}"
            try:
                async with sem, session.get(url, timeout=timeout) as resp:
                    html = await resp.text()
                    restricted = "This phone number is restricted on Telegram" in html
            except:
                restricted = None
            _set_cache(num, restricted)
            return num, restricted

        async with aiohttp.ClientSession(connector=conn, headers=_DEFAULT_HEADERS) as sess:
            results = await asyncio.gather(*(fetch(n, sess) for n in nums))

        restricted = [n for n, ok in results if ok]
        unknown    = [n for n, ok in results if ok is None]

        if restricted:
            content = "\n".join(
                f"🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>"
                for n in restricted
            )
        else:
            content = "✅ No restricted numbers found."

        if unknown:
            content += "\n\n⚠️ Could not verify:\n" + "\n".join(unknown)

    article = InlineQueryResultArticle(
        id="check_restricted",
        title="Restricted Numbers",
        input_message_content=InputTextMessageContent(content),
    )
    await inline_query.answer([article], cache_time=0)
