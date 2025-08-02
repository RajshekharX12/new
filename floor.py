#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Scrapes fragment.com/numbers?filter=sale with BeautifulSoup
  • Finds the first '/number/888…/code' link
  • Follows it, parses TON and USD prices
  • Replies with "+888…: <TON> TON (~$<USD>)"
"""

import sys
import re
import logging
import requests
from bs4 import BeautifulSoup
from aiogram.filters import Command
from aiogram.types import Message

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp
bot   = _main.bot

logger = logging.getLogger(__name__)

# session with real browser UA
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
        # 1) GET the sale listings page
        list_url = "https://fragment.com/numbers?filter=sale"
        r = session.get(list_url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # 2) Find the first +888 link
        link = None
        for a in soup.find_all("a", href=True):
            if re.match(r"^/number/888\d+/code$", a["href"]):
                link = a["href"]
                break
        if not link:
            raise ValueError("No +888 listings found on sale page")

        number = "+" + link.split("/")[2]

        # 3) GET the detail page
        detail = session.get(f"https://fragment.com{link}", timeout=10)
        detail.raise_for_status()
        dsoup = BeautifulSoup(detail.text, "html.parser")

        # 4) Parse TON and USD
        ton_text = dsoup.find(text=re.compile(r"\d[\d,]*\s*TON"))
        usd_text = dsoup.find(text=re.compile(r"~\s*\$\d[\d,]*"))
        if not ton_text or not usd_text:
            raise ValueError("Could not locate price info")
        ton = re.search(r"([\d,]+)\s*TON", ton_text).group(1).replace(",", "")
        usd = re.search(r"\$(\d[\d,]*)", usd_text).group(1).replace(",", "")

        # 5) Reply
        await status.delete()
        await message.answer(f"💰 {number}: {ton} TON (~${usd})")

    except Exception as e:
        logger.exception("floor error")
        await status.edit_text(f"❌ Failed to fetch floor: {e}")
