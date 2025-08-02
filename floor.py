#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Scrapes the fragment.com sale listings (SSR) with a proper User-Agent
  • Finds the first +888 listing link
  • Fetches its detail page
  • Extracts and reports TON price and USD equivalent
"""

import sys
import re
import logging
import requests
from aiogram.filters import Command
from aiogram.types import Message

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp
bot   = _main.bot

logger = logging.getLogger(__name__)

# warm up a session with a real browser UA
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
})

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        # 1) Fetch the sale listings page
        list_url = "https://fragment.com/numbers?filter=sale"
        resp = session.get(list_url, timeout=10)
        resp.raise_for_status()
        html_text = resp.text

        # 2) Find the first +888 listing link (SSR)
        m = re.search(r'href=[\'"](/number/888\d+/code)[\'"]', html_text)
        if not m:
            raise ValueError("No +888 listings found in page HTML")
        path   = m.group(1)  # e.g. /number/88804686913/code
        number = path.split("/")[2]  # e.g. 88804686913

        # 3) Fetch the detail page
        detail_url  = f"https://fragment.com{path}"
        detail_resp = session.get(detail_url, timeout=10)
        detail_resp.raise_for_status()
        detail_html = detail_resp.text

        # 4) Extract TON price and USD equivalent
        ton_m = re.search(r'(\d+)\s*TON\b', detail_html)
        usd_m = re.search(r'~\s*\$([\d,]+)', detail_html)
        if not ton_m or not usd_m:
            raise ValueError("Could not parse price information")
        ton = ton_m.group(1)
        usd = usd_m.group(1)

        # 5) Send the result
        await status.delete()
        await message.answer(
            f"💰 Current Floor Number: +{number}\n\n"
            f"• Price: {ton} TON (~${usd})"
        )

    except Exception as e:
        logger.exception("floor error")
        await status.edit_text(f"❌ Failed to fetch floor: {e}")
