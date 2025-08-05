import os
import sys
import re
import json
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

# Load existing saves (or start fresh)
try:
    with open(STORAGE_FILE, encoding="utf-8") as f:
        raw = json.load(f)
        _saves = {int(k): v for k, v in raw.items()}
except (FileNotFoundError, json.JSONDecodeError):
    _saves = {}

def _persist():
    """Write the in-memory `_saves` back to disk."""
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(_saves, f, ensure_ascii=False)

# ─── Boilerplate & Globals ────────────────────────────────────────
logger = logging.getLogger(__name__)
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}
MAX_SAVE = 400

# grab dispatcher & bot from main
_main = sys.modules.get("__main__")
dp = getattr(_main, "dp", None)

def _user_id(msg: Message) -> int:
    return msg.from_user.id

# ─── /save ─────────────────────────────────────────────────────────
@dp.message(Command("save"))
async def save_numbers(message: Message):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply(
            "⚠️ Usage: `/save <num1> [<num2> …]`", parse_mode="Markdown"
        )

    tokens = re.split(r"[,\|\n]+", parts[1])
    user = _user_id(message)
    current = _saves.setdefault(user, [])
    added = 0

    for tok in tokens:
        num = re.sub(r"\D", "", tok)
        if num and len(current) < MAX_SAVE and num not in current:
            current.append(num)
            added += 1

    _persist()
    await message.reply(
        f"✅ Added {added} number{'s' if added != 1 else ''}. "
        f"Total stored: {len(current)}/{MAX_SAVE}."
    )

# ─── /list ─────────────────────────────────────────────────────────
@dp.message(Command("list"))
async def list_numbers(message: Message):
    user = _user_id(message)
    nums = _saves.get(user, [])
    if not nums:
        return await message.reply("📭 No numbers saved.")
    await message.reply("Saved (count: {}):\n{}".format(len(nums), "\n".join(nums)))

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
        return await message.reply("📭 No numbers saved. Use /save first.")

    status = await message.reply(f"⏳ Checking {len(nums)} numbers…")

    sem = asyncio.Semaphore(min(len(nums), 100))
    timeout = aiohttp.ClientTimeout(total=8)
    connector = aiohttp.TCPConnector(limit_per_host=100)
    results: list[tuple[str, bool | None]] = [("", False)] * len(nums)

    async def fetch(i: int, number: str, session: aiohttp.ClientSession):
        url = f"https://fragment.com/phone/{number}"
        try:
            async with sem, session.get(url, timeout=timeout) as resp:
                html_text = await resp.text()
                restricted = "This phone number is restricted on Telegram" in html_text
                results[i] = (number, restricted)
        except Exception as e:
            logger.warning(f"Fetch failed for {number}: {e}")
            results[i] = (number, None)

    async with aiohttp.ClientSession(connector=connector, headers=DEFAULT_HEADERS) as session:
        await asyncio.gather(*(fetch(i, n, session) for i, n in enumerate(nums)))

    restricted = [n for n, ok in results if ok]
    unknown = [n for n, ok in results if ok is None]

    if restricted:
        for chunk in [restricted[i:i+30] for i in range(0, len(restricted), 30)]:
            lines = "\n".join(
                f"🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>"
                for n in chunk
            )
            await message.reply(lines, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await message.reply("❌ No restricted numbers found.")

    if unknown:
        await message.reply("⚠️ Could not verify:\n" + "\n".join(unknown))

    await status.delete()

# ─── Inline handler ───────────────────────────────────────────────
@dp.inline_query()
async def inline_check(inline_query: InlineQuery):
    user = inline_query.from_user.id
    nums = _saves.get(user, [])
    if not nums:
        content = "📭 No numbers saved. Use /save first."
    else:
        sem = asyncio.Semaphore(min(len(nums), 100))
        timeout = aiohttp.ClientTimeout(total=5)
        connector = aiohttp.TCPConnector(limit_per_host=100)
        results: list[tuple[str, bool | None]] = [("", False)] * len(nums)

        async def fetch(i: int, number: str, session: aiohttp.ClientSession):
            url = f"https://fragment.com/phone/{number}"
            try:
                async with sem, session.get(url, timeout=timeout) as resp:
                    html_text = await resp.text()
                    restricted = "This phone number is restricted on Telegram" in html_text
                    results[i] = (number, restricted)
            except:
                results[i] = (number, None)

        async with aiohttp.ClientSession(connector=connector, headers=DEFAULT_HEADERS) as session:
            await asyncio.gather(*(fetch(i, n, session) for i, n in enumerate(nums)))

        restricted = [n for n, ok in results if ok]
        unknown = [n for n, ok in results if ok is None]

        if restricted:
            content = "\n".join(
                f"🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>"
                for n in restricted
            )
        else:
            content = "❌ No restricted numbers found."

        if unknown:
            content += "\n\n⚠️ Could not verify:\n" + "\n".join(unknown)

    article = InlineQueryResultArticle(
        id="check_restricted",
        title="Restricted Numbers",
        input_message_content=InputTextMessageContent(content),
    )
    await inline_query.answer([article], cache_time=0)
