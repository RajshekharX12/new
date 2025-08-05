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
dp = getattr(_main, "dp", None)

logger = logging.getLogger(__name__)
_saves: dict[int, list[str]] = {}   # chat_id -> list of canonical numbers
MAX_SAVE = 400

@dp.message(Command("save"))
async def save_numbers(message: Message):
    """
    Save up to 400 phone numbers (removing any spaces/punctuation).
    Usage: /save +888 0403 7649 | +1234567890, +19876543210
    """
    # Extract everything after the command
    text = message.text.strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply(
            "⚠️ Usage: `/save <num1> [<num2> ...]`",
            parse_mode="Markdown"
        )

    raw = parts[1]
    # Split on pipes, commas or newlines
    tokens = re.split(r"[,\|\n]+", raw)
    chat_id = message.chat.id
    current = _saves.get(chat_id, [])
    added = 0

    for tok in tokens:
        # Remove all non-digits
        num = re.sub(r"\D", "", tok)
        if not num or len(current) >= MAX_SAVE:
            continue
        if num not in current:
            current.append(num)
            added += 1

    _saves[chat_id] = current
    await message.reply(
        f"✅ Added {added} number{'s' if added!=1 else ''}. "
        f"Total stored: {len(current)}/{MAX_SAVE}."
    )

@dp.message(Command("list"))
async def list_numbers(message: Message):
    """List all saved numbers for this chat."""
    chat_id = message.chat.id
    nums = _saves.get(chat_id, [])
    if not nums:
        return await message.reply("📭 No numbers saved.")
    text = "Saved numbers (count: {}):\n".format(len(nums)) + "\n".join(nums)
    await message.reply(text)

@dp.message(Command("clear"))
async def clear_numbers(message: Message):
    """Clear all saved numbers for this chat."""
    chat_id = message.chat.id
    _saves.pop(chat_id, None)
    await message.reply("🗑️ All saved numbers have been cleared.")

@dp.message(Command("checkall"))
async def check_all(message: Message):
    """
    Check restriction status for all saved numbers concurrently.
    Uses 🔒 for restricted numbers.
    """
    chat_id = message.chat.id
    nums = _saves.get(chat_id, [])
    if not nums:
        return await message.reply("📭 No numbers saved. Use /save first.")

    status = await message.reply(f"⏳ Checking {len(nums)} numbers…")

    sem = asyncio.Semaphore(min(len(nums), 100))
    timeout = aiohttp.ClientTimeout(total=8)   # total per request
    results: list[tuple[str,bool|None]] = [None] * len(nums)

    async def fetch(i: int, number: str, session: aiohttp.ClientSession):
        url = f"https://fragment.com/phone/{number}"
        async with sem:
            try:
                async with session.get(url, timeout=timeout) as resp:
                    html = await resp.text()
                    # The page shows this banner when the number is restricted:
                    is_restricted = "This phone number is restricted on Telegram" in html
                    results[i] = (number, is_restricted)
            except Exception as e:
                logger.warning(f"Fetch failed for {number}: {e}")
                results[i] = (number, None)

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(fetch(i, n, session) for i, n in enumerate(nums)))

    # Collect only those flagged restricted==True
    restricted = [num for num, ok in results if ok]
    if restricted:
        # Telegram can only show so much in one message, chunk by 30
        for chunk in [restricted[i:i+30] for i in range(0, len(restricted), 30)]:
            await message.reply("\n".join(f"🔒 {n}" for n in chunk))
    else:
        await message.reply("❌ No restricted numbers found.")

    await status.delete()

@dp.inline_query()
async def inline_check(inline_query: InlineQuery):
    """
    Inline handler (press @bot in any chat + 'check'):
    Returns only restricted numbers, prefixed with 🔒
    """
    user_id = inline_query.from_user.id
    nums = _saves.get(user_id, [])
    if not nums:
        content = "📭 No numbers saved. Use /save first."
    else:
        sem = asyncio.Semaphore(min(len(nums), 100))
        timeout = aiohttp.ClientTimeout(total=5)
        results: list[tuple[str,bool|None]] = [None] * len(nums)

        async with aiohttp.ClientSession() as session:
            async def fetch(i: int, number: str):
                async with sem:
                    try:
                        resp = await session.get(
                            f"https://fragment.com/phone/{number}",
                            timeout=timeout
                        )
                        html = await resp.text()
                        is_restricted = "This phone number is restricted on Telegram" in html
                        results[i] = (number, is_restricted)
                    except:
                        results[i] = (number, None)

            await asyncio.gather(*(fetch(i, n) for i, n in enumerate(nums)))

        restricted = [num for num, ok in results if ok]
        if restricted:
            content = "\n".join(f"🔒 {n}" for n in restricted)
        else:
            content = "❌ No restricted numbers found."

    article = InlineQueryResultArticle(
        id="check_restricted",
        title="Restricted Numbers",
        input_message_content=InputTextMessageContent(content),
    )
    await inline_query.answer([article], cache_time=0)
