# fragment.py
import sys
import os
import re
import json
import asyncio
import logging

import aiohttp
from aiogram.filters import Command
from aiogram.types import Message, InlineQuery, InlineQueryResultArticle, InputTextMessageContent

# grab dispatcher from main bot.py
_main = sys.modules["__main__"]
dp    = getattr(_main, "dp")

logger = logging.getLogger(__name__)

# ─── persistence setup ─────────────────────────────────────────────
_SAVES_FILE = os.path.join(os.getcwd(), "saves.json")
_saves: dict[int, list[str]] = {}  # user_id → list of canonical numbers
_MAX_SAVE = 400

def load_saves():
    global _saves
    if os.path.isfile(_SAVES_FILE):
        with open(_SAVES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # keys come back as strings
        _saves = {int(k): v for k, v in data.items()}

def save_saves():
    with open(_SAVES_FILE, "w", encoding="utf-8") as f:
        json.dump(_saves, f, ensure_ascii=False)

# load at import time
load_saves()

# ─── HTTP client defaults ──────────────────────────────────────────
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}

# ─── helpers ───────────────────────────────────────────────────────
def _canonical(tok: str) -> str:
    return re.sub(r"\D", "", tok)

def _user_id(msg: Message) -> int:
    return msg.from_user.id

# ─── /save handler ─────────────────────────────────────────────────
@dp.message(Command("save"))
async def save_numbers(message: Message):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("⚠️ Usage: `/save <num1>[,| ]<num2> …`", parse_mode="Markdown")

    raw = re.split(r"[,\s]+", parts[1])
    uid = _user_id(message)
    store = _saves.setdefault(uid, [])
    added = 0

    for tok in raw:
        num = _canonical(tok)
        if num and len(store) < _MAX_SAVE and num not in store:
            store.append(num)
            added += 1

    save_saves()
    await message.reply(f"✅ Added {added} number(s). Total stored: {len(store)}/{_MAX_SAVE}.")

# ─── /clearall handler ─────────────────────────────────────────────
@dp.message(Command("clearall"))
async def clear_numbers(message: Message):
    uid = _user_id(message)
    if uid in _saves:
        _saves.pop(uid)
        save_saves()
    await message.reply("🗑️ All your saved numbers have been cleared.")

# ─── /checkall handler ─────────────────────────────────────────────
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
        url = f"https://fragment.com/phone/{num}"
        try:
            async with sem, session.get(url, timeout=timeout) as resp:
                text = await resp.text()
                restricted = "This phone number is restricted on Telegram" in text
        except Exception as e:
            logger.warning(f"Fetch failed for {num}: {e}")
            restricted = None
        return num, restricted

    async with aiohttp.ClientSession(connector=conn, headers=_DEFAULT_HEADERS) as sess:
        results = await asyncio.gather(*(fetch(n, sess) for n in nums))

    await status.delete()

    # extract restricted + unknown
    restricted = [n for n, ok in results if ok]
    unknown    = [n for n, ok in results if ok is None]

    # send restricted, numbered
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
            header = ""  # only on first chunk
    else:
        await message.reply(f"✅ No restricted numbers out of {len(nums)} checked.")

    # report any that errored
    if unknown:
        await message.reply("⚠️ Could not verify:\n" + "\n".join(unknown))

# ─── inline @bot check query ───────────────────────────────────────
@dp.inline_query()
async def inline_check(inline_q: InlineQuery):
    uid  = inline_q.from_user.id
    nums = _saves.get(uid, [])
    if not nums:
        content = "📭 No numbers saved. Use `/save` first."
    else:
        # same logic, but inline
        sem     = asyncio.Semaphore(min(len(nums), 100))
        timeout = aiohttp.ClientTimeout(total=5)
        conn    = aiohttp.TCPConnector(limit_per_host=100)

        async def fetch(num: str, session: aiohttp.ClientSession):
            url = f"https://fragment.com/phone/{num}"
            try:
                async with sem, session.get(url, timeout=timeout) as resp:
                    text = await resp.text()
                    restricted = "This phone number is restricted on Telegram" in text
            except:
                restricted = None
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
        id="restricted",
        title="⚒ Restricted Numbers",
        input_message_content=InputTextMessageContent(content, parse_mode="HTML")
    )
    await inline_q.answer([article], cache_time=0)
