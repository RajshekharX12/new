#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Scrapes fragment.com/numbers?filter=sale
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

# set up a session with a browser‐like UA
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
        # 1) Fetch the listings page
        list_url = "https://fragment.com/numbers?filter=sale"
        r = session.get(list_url, timeout=10)
        r.raise_for_status()
        html = r.text

        # 2) Extract the first +888 detail path
        m = re.search(r'href="(/number/888[0-9]+/code)"', html)
        if not m:
            raise ValueError("No +888 listings found on the sale page")
        path   = m.group(1)                # e.g. /number/88804686913/code
        number = path.split("/")[2]        # e.g. 88804686913

        # 3) Fetch the detail page
        detail_url = f"https://fragment.com{path}"
        rd = session.get(detail_url, timeout=10)
        rd.raise_for_status()
        dhtml = rd.text

        # 4) Parse TON price (e.g. "720 TON")
        m_ton = re.search(r'([\d,]+)\s*TON\b', dhtml)
        if not m_ton:
            raise ValueError("Couldn't parse TON price")
        ton = m_ton.group(1).replace(",", "")

        # 5) Parse USD equivalent (e.g. "~ $2,602")
        m_usd = re.search(r'~\s*\$([\d,]+)', dhtml)
        usd = m_usd.group(1).replace(",", "") if m_usd else "N/A"

        # 6) Report back
        await status.delete()
        await message.answer(
            f"💰 Current Floor Number: +{number}\n\n"
            f"• Price: {ton} TON (~${usd})"
        )

    except Exception as e:
        logger.exception("floor error")
        await status.edit_text(f"❌ Failed to fetch floor: {e}")
