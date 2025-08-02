#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Uses cloudscraper to fetch the JSON sale listings
  • Grabs the first +888 number and its TON/USD prices
"""

import logging
import cloudscraper
from aiogram.filters import Command
from aiogram.types import Message

# grab dispatcher & bot from main
import sys
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)
scraper = cloudscraper.create_scraper()

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        # 1) Fetch JSON directly
        url = "https://fragment.com/api/numbers?filter=sale"
        resp = scraper.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # 2) Get the first node
        nodes = data.get("nodes") or data.get("data") or data
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("No sale listings in JSON")

        first = nodes[0]
        number = first.get("number")
        # TON price might be under assetPrice.value or tokenPrice
        ton = None
        ap = first.get("assetPrice") or first.get("tokenPrice")
        if isinstance(ap, dict):
            ton = ap.get("value")
        elif isinstance(ap, (int, float, str)):
            ton = ap

        usd = first.get("fiatPrice") or first.get("usdPrice") or first.get("priceUsd")
        if not (number and ton and usd):
            raise ValueError("Incomplete price info in JSON")

        # 3) Reply
        await status.delete()
        await message.answer(
            f"💰 +{number}: {ton} TON (~${usd})"
        )

    except Exception as e:
        logger.exception("floor error")
        from html import escape
        safe = escape(str(e))
        await status.edit_text(
            f"❌ Failed to fetch floor:\n```{safe}```",
            parse_mode="Markdown"
        )
