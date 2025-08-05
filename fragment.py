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
_saves: dict[int, list[str]] = {}   # user_id → list of canonical numbers
MAX_SAVE = 400

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}


def _user_id(ctx):
    return ctx.from_user.id


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
        if num and len(current) < MAX_SAVE and num not in current:
            current.append(num)
            added += 1

    await message.reply(
        f"✅ Added {added} number{'s' if added != 1 else ''}. "
        f"Total stored: {len(current)}/{MAX_SAVE}."
    )


@dp.message(Command("list"))
async def list_numbers(message: Message):
    user = _user_id(message)
    nums = _saves.get(user, [])
    if not nums:
        return await message.reply("📭 No numbers saved.")
    await message.reply("Saved (count: {}):\n{}".format(len(nums), "\n".join(nums)))


@dp.message(Command(commands=["clear", "clearall"]))
async def clear_numbers(message: Message):
    user = _user_id(message)
    _saves.pop(user, None)
    await message.reply("🗑️ All your saved numbers have been cleared.")


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
        Returns True if number is restricted (or on error),
        False otherwise.
        """
        url = f"https://fragment.com/phone/{number}"
        try:
            async with sem, session.get(url, timeout=timeout) as resp:
                text = await resp.text()
                return "This phone number is restricted on Telegram" in text
        except Exception as e:
            logger.warning(f"Error checking {number}: {e}")
            # Treat any failure as "restricted" to ensure no escapes
            return True

    async with aiohttp.ClientSession(connector=connector, headers=DEFAULT_HEADERS) as session:
        results = await asyncio.gather(
            *(fetch_status(n, session) for n in nums),
            return_exceptions=False
        )

    # Now every saved number was checked exactly once.
    restricted = [n for n, is_restricted in zip(nums, results) if is_restricted]

    if restricted:
        # Enumerate in ascending order
        lines = "\n".join(
            f"{idx+1}. 🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>"
            for idx, n in enumerate(restricted)
        )
        await message.reply(lines,
                            parse_mode="HTML",
                            disable_web_page_preview=True)
    else:
        await message.reply("✅ No restricted numbers found.")

    await status.delete()


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

        restricted = [n for n, is_restricted in zip(nums, results) if is_restricted]

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
