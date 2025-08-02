#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  1) Try the JSON API for sale listings
  2) If empty, fetch the HTML sale page & regex–find the first +888 link
  3) Fetch its detail page and extract TON/USD via regex
"""

import re
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
        # 1) JSON attempt
        api_url = "https://fragment.com/api/numbers?filter=sale"
        r = scraper.get(api_url, timeout=10)
        r.raise_for_status()
        data = r.json() or {}
        nodes = data.get("nodes") or data.get("data") or []
        first = next((n for n in nodes if str(n.get("number","")).startswith("888")), None)

        # 2) Fallback to HTML if JSON empty
        if not first:
            list_page = scraper.get("https://fragment.com/numbers?filter=sale", timeout=10).text
            m_link = re.search(r'href="(/number/(888\d+)/code)"', list_page)
            if not m_link:
                raise ValueError("No +888 listing found in JSON or page HTML")
            path   = m_link.group(1)
            number = m_link.group(2)
            detail = scraper.get(f"https://fragment.com{path}", timeout=10).text

            ton_m = re.search(r"([\d,]+)\s*TON\b", detail)
            usd_m = re.search(r"~\s*\$([\d,.,]+)", detail)
            if not ton_m or not usd_m:
                raise ValueError("Could not parse prices from detail page")
            ton = ton_m.group(1).replace(",", "")
            usd = usd_m.group(1).replace(",", "")
        else:
            # JSON succeeded
            number = str(first["number"])
            ap = first.get("assetPrice") or first.get("tokenPrice") or first.get("price")
            ton = (ap.get("value") if isinstance(ap, dict) else ap) or "N/A"
            usd = first.get("fiatPrice") or first.get("usdPrice") or first.get("priceUsd") or "N/A"

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
