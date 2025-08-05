# fragment.py
import sys
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
_saves = {}  # chat_id -> list of phone numbers
MAX_SAVE = 400

@dp.message(Command("save"))
async def save_numbers(message: Message):
    """Save up to 400 phone numbers inline: /save num1 num2 num3 ..."""
    parts = message.text.strip().split()[1:]
    if not parts:
        return await message.reply("⚠️ Usage: `/save <number1> <number2> ...`", parse_mode="Markdown")
    chat_id = message.chat.id
    current = _saves.get(chat_id, [])
    for num in parts:
        if len(current) >= MAX_SAVE:
            break
        if num not in current:
            current.append(num)
    _saves[chat_id] = current
    await message.reply(f"✅ Saved {len(parts)} numbers. Total stored: {len(current)}/{MAX_SAVE}.")

@dp.message(Command("list"))
async def list_numbers(message: Message):
    """List all currently saved numbers."""
    chat_id = message.chat.id
    nums = _saves.get(chat_id, [])
    if not nums:
        return await message.reply("📭 No numbers saved.")
    text = "Saved numbers (count: {}):\n".format(len(nums)) + "\n".join(nums)
    await message.reply(text)

@dp.message(Command("checkall"))
async def check_all(message: Message):
    """Check restriction status for all saved numbers concurrently in ~5s, returns only restricted."""
    chat_id = message.chat.id
    nums = _saves.get(chat_id, [])
    if not nums:
        return await message.reply("📭 No numbers saved. Use /save first.")
    status = await message.reply(f"⏳ Checking {len(nums)} numbers…")

    sem = asyncio.Semaphore(min(len(nums), 100))
    timeout = aiohttp.ClientTimeout(total=10)
    results = [None] * len(nums)

    async def fetch(i, number, session):
        url = f"https://fragment.com/phone/{number}"
        async with sem:
            try:
                async with session.get(url, timeout=timeout) as resp:
                    results[i] = (number, resp.status != 404)
            except Exception:
                results[i] = (number, None)

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(fetch(i, n, session) for i, n in enumerate(nums)))

    restricted = [num for num, ok in results if ok]
    if restricted:
        chunks = [restricted[i:i+30] for i in range(0, len(restricted), 30)]
        for chunk in chunks:
            await message.reply("\n".join(f"✅ {n}" for n in chunk))
    else:
        await message.reply("❌ No restricted numbers found.")
    await status.delete()

@dp.inline_query()
async def inline_check(inline_query: InlineQuery):
    """Inline handler: @bot check — returns restricted numbers only."""
    user_id = inline_query.from_user.id
    nums = _saves.get(user_id, [])
    if not nums:
        content = "📭 No numbers saved. Use /save first."
    else:
        sem = asyncio.Semaphore(min(len(nums), 100))
        timeout = aiohttp.ClientTimeout(total=5)
        results = [None] * len(nums)
        async with aiohttp.ClientSession() as session:
            async def fetch(i, number):
                async with sem:
                    try:
                        resp = await session.get(f"https://fragment.com/phone/{number}", timeout=timeout)
                        results[i] = (number, resp.status != 404)
                    except:
                        results[i] = (number, None)
            await asyncio.gather(*(fetch(i, n) for i, n in enumerate(nums)))
        restricted = [num for num, ok in results if ok]
        content = "\n".join(f"✅ {n}" for n in restricted) if restricted else "❌ No restricted numbers found."
    article = InlineQueryResultArticle(
        id="check_restricted",
        title="Restricted Numbers",
        input_message_content=InputTextMessageContent(content)
    )
    await inline_query.answer([article], cache_time=0)
