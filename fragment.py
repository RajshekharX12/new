# fragment.py
import sys
import re
import asyncio
import logging
import random
import time

import aiohttp
from bs4 import BeautifulSoup
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

# grab dispatcher & bot
_main = sys.modules.get("__main__")
dp    = getattr(_main, "dp", None)

logger = logging.getLogger(__name__)
_saves: dict[int, list[str]] = {}    # user_id → list of canonical numbers
MAX_SAVE = 400

# A small pool of common desktop/mobile UAs
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/115.0.0.0 Mobile Safari/537.36",
]

HEAD_TIMEOUT = aiohttp.ClientTimeout(total=4)
GET_TIMEOUT  = aiohttp.ClientTimeout(total=8)
CONN_LIMIT   = 100
RESTRICTED_PHRASES = [
    "This phone number is restricted on Telegram",
    "restricted on Telegram",
    "Number is restricted",
]

def _user_id(ctx):
    return ctx.from_user.id

@dp.message(Command("save"))
async def save_numbers(message: Message):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await message.reply("⚠️ Usage: `/save <num1> [<num2> ...]`", parse_mode="Markdown")

    raw = parts[1]
    tokens = re.split(r"[,\|\n]+", raw)
    user = _user_id(message)
    current = _saves.setdefault(user, [])
    added = 0

    for tok in tokens:
        num = re.sub(r"\D", "", tok)
        if num and len(current) < MAX_SAVE and num not in current:
            current.append(num)
            added += 1

    await message.reply(f"✅ Added {added} number{'s' if added!=1 else ''}. Total: {len(current)}/{MAX_SAVE}.")

@dp.message(Command("list"))
async def list_numbers(message: Message):
    user = _user_id(message)
    nums = _saves.get(user, [])
    if not nums:
        return await message.reply("📭 No numbers saved.")
    await message.reply("Saved ({}):\n{}".format(len(nums), "\n".join(nums)))

@dp.message(Command(("clear","clearall")))
async def clear_numbers(message: Message):
    user = _user_id(message)
    _saves.pop(user, None)
    await message.reply("🗑️ Cleared your saved numbers.")

@dp.message(Command("checkall"))
async def check_all(message: Message):
    user = _user_id(message)
    nums = _saves.get(user, [])
    if not nums:
        return await message.reply("📭 No numbers saved. Use /save first.")

    status = await message.reply(f"⏳ Checking {len(nums)} numbers…")

    sem = asyncio.Semaphore(min(len(nums), 100))
    connector = aiohttp.TCPConnector(limit_per_host=CONN_LIMIT, ssl=False)
    results = [None] * len(nums)

    async def fetch(i: int, number: str):
        url = f"https://fragment.com/phone/{number}"
        headers = {"User-Agent": random.choice(USER_AGENTS)}

        # 1) HEAD to catch quick 404
        try:
            async with sem, aiohttp.ClientSession(connector=connector, timeout=HEAD_TIMEOUT, headers=headers) as session:
                resp = await session.head(url)
                if resp.status == 404:
                    results[i] = (number, True)  # definitely restricted
                    return
        except Exception as e:
            logger.debug(f"HEAD failed for {number}: {e}")

        # 2) GET + parse
        backoff = 1.0
        for attempt in (1, 2):
            try:
                async with sem, aiohttp.ClientSession(connector=connector, timeout=GET_TIMEOUT, headers=headers) as session:
                    resp = await session.get(url)
                    text = await resp.text()
                    soup = BeautifulSoup(text, "html.parser")
                    body = soup.get_text(separator=" ", strip=True)
                    # case-insensitive search for any of the restricted phrases
                    restricted = any(phrase.lower() in body.lower() for phrase in RESTRICTED_PHRASES)
                    results[i] = (number, restricted)
                    return
            except Exception as e:
                logger.debug(f"GET attempt {attempt} failed for {number}: {e}")
                await asyncio.sleep(backoff)
                backoff *= 2

        # fallback: treat as unchecked
        results[i] = (number, None)

    # launch all fetches
    await asyncio.gather(*(fetch(i, n) for i, n in enumerate(nums)))

    # partition
    restricted = [n for n, ok in results if ok is True]
    unknown    = [n for n, ok in results if ok is None]

    # send restricted with 🔒 links
    if restricted:
        for chunk in [restricted[i:i+30] for i in range(0, len(restricted), 30)]:
            msg = "\n".join(
                f"🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>"
                for n in chunk
            )
            await message.reply(msg, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await message.reply("❌ No restricted numbers found.")

    # report unknowns
    if unknown:
        await message.reply("⚠️ Could not verify:\n" + "\n".join(unknown))

    await status.delete()

@dp.inline_query()
async def inline_check(inline_query):
    user = inline_query.from_user.id
    nums = _saves.get(user, [])
    if not nums:
        content = "📭 No numbers saved. Use /save first."
    else:
        sem = asyncio.Semaphore(min(len(nums), 100))
        connector = aiohttp.TCPConnector(limit_per_host=CONN_LIMIT, ssl=False)
        results = [None] * len(nums)

        async def fetch(i: int, number: str):
            url = f"https://fragment.com/phone/{number}"
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            try:
                async with sem, aiohttp.ClientSession(connector=connector, timeout=HEAD_TIMEOUT, headers=headers) as session:
                    resp = await session.head(url)
                    if resp.status == 404:
                        results[i] = (number, True)
                        return
            except:
                pass

            try:
                async with sem, aiohttp.ClientSession(connector=connector, timeout=GET_TIMEOUT, headers=headers) as session:
                    resp = await session.get(url)
                    text = await resp.text()
                    body = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
                    restricted = any(p.lower() in body.lower() for p in RESTRICTED_PHRASES)
                    results[i] = (number, restricted)
            except:
                results[i] = (number, None)

        await asyncio.gather(*(fetch(i, n) for i, n in enumerate(nums)))

        restricted = [n for n, ok in results if ok is True]
        unknown    = [n for n, ok in results if ok is None]

        if restricted:
            content = "\n".join(f"🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>" for n in restricted)
        else:
            content = "❌ No restricted numbers found."
        if unknown:
            content += "\n\n⚠️ Could not verify:\n" + "\n".join(unknown)

    result = InlineQueryResultArticle(
        id="check_restricted",
        title="Restricted Numbers",
        input_message_content=InputTextMessageContent(content),
    )
    await inline_query.answer([result], cache_time=0)
