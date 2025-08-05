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

# ─── Grab dispatcher from main ─────────────────────────────────────
_main = sys.modules.get("__main__")
dp    = getattr(_main, "dp", None)

# ─── Logging ──────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ─── In-memory per-user storage ────────────────────────────────────
# Keyed by Telegram user_id, not chat_id
_saves: dict[int, list[str]] = {}
MAX_SAVE = 400

# ─── HTTP settings ────────────────────────────────────────────────
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}

def _user_id(msg: Message) -> int:
    return msg.from_user.id

# ─── /save command ────────────────────────────────────────────────
@dp.message(Command("save"))
async def save_numbers(message: Message):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("⚠️ Usage: `/save <num1> [<num2> …]`", parse_mode="Markdown")
    tokens = re.split(r"[,\|\n]+", parts[1])
    user = _user_id(message)
    current = _saves.setdefault(user, [])
    added = 0
    for tok in tokens:
        num = re.sub(r"\D", "", tok)
        if not num:
            continue
        if len(current) >= MAX_SAVE:
            break
        if num not in current:
            current.append(num)
            added += 1
    await message.reply(
        f"✅ Added {added} number{'s' if added != 1 else ''}. "
        f"Total stored: {len(current)}/{MAX_SAVE}."
    )

# ─── /list command ────────────────────────────────────────────────
@dp.message(Command("list"))
async def list_numbers(message: Message):
    user = _user_id(message)
    nums = _saves.get(user, [])
    if not nums:
        return await message.reply("📭 You have no numbers saved.")
    await message.reply("📋 Your saved numbers:\n" + "\n".join(nums))

# ─── /clear and /clearall ─────────────────────────────────────────
@dp.message(Command(commands=["clear", "clearall"]))
async def clear_numbers(message: Message):
    user = _user_id(message)
    _saves.pop(user, None)
    await message.reply("🗑️ All your saved numbers have been cleared.")

# ─── /checkall command ────────────────────────────────────────────
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

    async def fetch_status(number: str, session: aiohttp.ClientSession) -> bool:
        """
        Returns True if the number is restricted (or on network error),
        False if explicitly found safe.
        """
        url = f"https://fragment.com/phone/{number}"
        try:
            async with sem, session.get(url, timeout=timeout) as resp:
                text = await resp.text()
                return "This phone number is restricted on Telegram" in text
        except Exception as e:
            logger.warning(f"Error checking {number}: {e}")
            # treat any error as restricted
            return True

    async with aiohttp.ClientSession(connector=connector, headers=DEFAULT_HEADERS) as session:
        results = await asyncio.gather(
            *(fetch_status(n, session) for n in nums),
            return_exceptions=False
        )

    restricted = [n for n, flag in zip(nums, results) if flag]

    if restricted:
        # Output numbered ascending list with links
        lines = "\n".join(
            f"{idx+1}. 🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>"
            for idx, n in enumerate(restricted)
        )
        await message.reply(lines, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await message.reply("✅ No restricted numbers found.")

    await status.delete()

# ─── Inline query handler ─────────────────────────────────────────
@dp.inline_query()
async def inline_check(inline_query: InlineQuery):
    user = inline_query.from_user.id
    nums = _saves.get(user, [])
    if not nums:
        content = "📭 No numbers saved. Use /save first."
    else:
        sem = asyncio.Semaphore(min(len(nums), 100))
        timeout = aiohttp.ClientTimeout(total=8)
        connector = aiohttp.TCPConnector(limit_per_host=100)

        async def fetch_status(number: str, session: aiohttp.ClientSession) -> bool:
            try:
                async with sem, session.get(f"https://fragment.com/phone/{number}", timeout=timeout) as resp:
                    text = await resp.text()
                    return "This phone number is restricted on Telegram" in text
            except:
                return True

        async with aiohttp.ClientSession(connector=connector, headers=DEFAULT_HEADERS) as session:
            results = await asyncio.gather(
                *(fetch_status(n, session) for n in nums),
                return_exceptions=False
            )

        restricted = [n for n, flag in zip(nums, results) if flag]
        if restricted:
            content = "\n".join(
                f"{idx+1}. 🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>"
                for idx, n in enumerate(restricted)
            )
        else:
            content = "✅ No restricted numbers found."

    article = InlineQueryResultArticle(
        id="check_restricted",
        title="Restricted Numbers",
        input_message_content=InputTextMessageContent(content),
    )
    await inline_query.answer([article], cache_time=0)
