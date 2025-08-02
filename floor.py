#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Uses Next.js data endpoint to fetch numbers JSON
  • Finds the first +888 collectible
  • Reports its TON price and USD equivalent
"""

import sys
import json
import logging
import requests
import re
from aiogram.filters import Command
from aiogram.types import Message

# Grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp
bot   = _main.bot

logger = logging.getLogger(__name__)

# Browser‐like session
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
})

def _find_listings(obj):
    """Recursively search for a list of dicts each having a 'number' key."""
    if isinstance(obj, dict):
        for v in obj.values():
            found = _find_listings(v)
            if found:
                return found
    elif isinstance(obj, list) and obj and isinstance(obj[0], dict) and "number" in obj[0]:
        return obj
    elif isinstance(obj, list):
        for item in obj:
            found = _find_listings(item)
            if found:
                return found
    return None

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        # 1) GET main page to extract buildId
        page_url = "https://fragment.com/numbers?filter=sale"
        r = session.get(page_url, timeout=10)
        r.raise_for_status()
        html = r.text

        # 2) Extract __NEXT_DATA__ JSON and its buildId
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not m:
            raise ValueError("Can't find Next.js data on page")
        next_data = json.loads(m.group(1))
        build_id = next_data.get("buildId")
        if not build_id:
            raise ValueError("No buildId in Next.js data")

        # 3) Fetch the JSON endpoint for this page
        json_url = f"https://fragment.com/_next/data/{build_id}/numbers.json?filter=sale"
        jr = session.get(json_url, timeout=10)
        jr.raise_for_status()
        data = jr.json()

        # 4) Locate the listings array
        listings = _find_listings(data)
        if not listings:
            raise ValueError("No listings found in page data")

        # 5) Find the first +888 entry
        first = next((x for x in listings if str(x.get("number","")).startswith("888")), None)
        if not first:
            raise ValueError("No +888 collectible in listings")

        number = first["number"]
        # Extract TON price from various possible fields
        ton = None
        for key in ("assetPrice", "tokenPrice", "price"):
            val = first.get(key)
            if isinstance(val, dict) and "value" in val:
                ton = val["value"]
            elif isinstance(val, (int, float, str)):
                ton = val
            if ton:
                break

        usd = first.get("fiatPrice") or first.get("usdPrice") or first.get("priceUsd")
        if ton is None or usd is None:
            raise ValueError("Incomplete price info in listing")

        # 6) Send the result
        await status.delete()
        await message.answer(
            f"💰 Current Floor Number: +{number}\n\n"
            f"• Price: {ton} TON (~${usd})"
        )

    except Exception as e:
        logger.exception("floor error")
        await status.edit_text(f"❌ Failed to fetch floor: {e}")
