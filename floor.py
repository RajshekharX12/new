#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Fetches the MarketApp collection page
  • Parses the floor price (TON) and its USD equivalent
  • Replies with "+888 floor: <TON> TON (~$<USD>)"
"""

import re
import logging
import requests

from aiogram.filters import Command
from aiogram.types import Message
from html import escape

# grab dispatcher & bot from main
import sys
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

MARKET_URL = (
    "https://marketapp.ws/collection/"
    "EQAOQdwdw8kGftJCSFgOErM1mBjYPe4DBPq8-AhF6vr9si5N/"
)

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching floor price from MarketApp…")
    try:
        # 1) GET the collection page
        r = session.get(MARKET_URL, timeout=10)
        r.raise_for_status()
        text = r.text

        # 2) Find the “Anonymous Telegram Numbers” section
        #    and grab the first TON/USD pair that follows it.
        snippet = re.split(
            r"Anonymous Telegram Numbers", text, maxsplit=1, flags=re.IGNORECASE
        )[-1]

        # 3) Regex for TON and USD: e.g. "696 ~$2,506"
        m = re.search(r"(\d{2,4})\s*~\$\s*([\d,.,]+)", snippet)
        if not m:
            raise ValueError("Could not parse TON/USD from page")

        ton = m.group(1)
        usd = m.group(2)

        # 4) Send result
        await status.delete()
        await message.answer(f"💰 +888 floor: {ton} TON (~${usd})")

    except Exception as e:
        logger.exception("floor error")
        msg = escape(str(e))
        await status.edit_text(
            f"❌ Failed to fetch floor:\n```{msg}```",
            parse_mode="Markdown"
        )
