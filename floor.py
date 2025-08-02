#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Fetches https://fragment.com/numbers?filter=sale
  • Finds the first /number/888…/code link in the HTML
  • Fetches its detail page
  • Extracts TON and USD prices via regex
  • Replies with "+888…: <TON> TON (~$<USD>)"
"""

import re
import logging
import requests
from aiogram.filters import Command
from aiogram.types import Message

# grab dispatcher & bot from main
import sys
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        # 1) GET the sale listing HTML
        list_url = "https://fragment.com/numbers?filter=sale"
        r = session.get(list_url, timeout=10)
        r.raise_for_status()

        # 2) Find the first +888 detail path
        m = re.search(r'href="(/number/888\d+/code)"', r.text)
        if not m:
            raise ValueError("No +888 listing found on sale page")
        path   = m.group(1)                # e.g. /number/88804686913/code
        number = path.split("/")[2]        # e.g. 88804686913

        # 3) GET the detail page
        d = session.get(f"https://fragment.com{path}", timeout=10)
        d.raise_for_status()

        # 4) Parse TON price (e.g. "720 TON") and USD (e.g. "~ $2602")
        ton_m = re.search(r"([\d,]+)\s*TON", d.text)
        usd_m = re.search(r"~\s*\$([\d,.,]+)", d.text)
        if not ton_m or not usd_m:
            raise ValueError("Could not parse prices from detail page")

        ton = ton_m.group(1).replace(",", "")
        usd = usd_m.group(1).replace(",", "")

        # 5) Reply
        await status.delete()
        await message.answer(f"💰 +{number}: {ton} TON (~${usd})")

    except Exception as e:
        logger.exception("floor error")
        from html import escape
        safe = escape(str(e))
        await status.edit_text(
            f"❌ Failed to fetch floor:\n```{safe}```",
            parse_mode="Markdown"
        )
