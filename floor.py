#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Scrapes the fragment.com sale listings
  • Finds the first +888 number
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

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        # 1) Fetch the sale listings page
        list_url = "https://fragment.com/numbers?filter=sale"
        resp = requests.get(list_url, timeout=10)
        html_text = resp.text

        # 2) Find the first listing link
        m = re.search(r'href="(/number/\d+/code)"', html_text)
        if not m:
            raise ValueError("No +888 listings found")
        path   = m.group(1)  # e.g. /number/88804686913/code
        number = path.split("/")[2]  # e.g. 88804686913

        # 3) Fetch the detail page for that number
        detail_url  = f"https://fragment.com{path}"
        detail_resp = requests.get(detail_url, timeout=10)
        detail_html = detail_resp.text

        # 4) Extract TON price and USD equivalent
        ton_match = re.search(r'([\d,]+)\s*TON', detail_html)
        usd_match = re.search(r'~\s*\$([\d,.,]+)', detail_html)
        if not (ton_match and usd_match):
            raise ValueError("Unable to parse price info")

        ton = ton_match.group(1).replace(",", "")
        usd = usd_match.group(1).replace(",", "")

        # 5) Send the result
        await status.delete()
        await message.answer(
            f"💰 Current Floor Number: +{number}\n\n"
            f"• Price: {ton} TON (~${usd})"
        )

    except Exception as e:
        logger.exception("floor error")
        await status.edit_text(f"❌ Failed to fetch floor: {e}")
