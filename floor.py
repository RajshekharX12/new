#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Loads the sale page’s __NEXT_DATA__ JSON
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

# grab dispatcher from main
_main = sys.modules["__main__"]
dp    = _main.dp
bot   = _main.bot

logger = logging.getLogger(__name__)

# Browser-like session
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
})

def _find_listings(obj):
    """Recursively search for a list of dicts that each have a 'number' key."""
    if isinstance(obj, dict):
        # often in NextData: obj["props"]["pageProps"]["listings"]["nodes"]
        for k, v in obj.items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and "number" in v[0]:
                return v
            res = _find_listings(v)
            if res:
                return res
    elif isinstance(obj, list):
        for item in obj:
            res = _find_listings(item)
            if res:
                return res
    return None

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        # 1) GET the page
        url  = "https://fragment.com/numbers?filter=sale"
        resp = session.get(url, timeout=10)
        resp.raise_for_status()

        # 2) Extract the JSON blob
        m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', resp.text, re.DOTALL)
        if not m:
            raise ValueError("Unable to find Next.js data on page")
        data = json.loads(m.group(1))

        # 3) Locate the listings array
        listings = _find_listings(data)
        if not listings:
            raise ValueError("No listings array found in page data")

        # 4) Pick the first +888 entry
        first = next((item for item in listings if str(item.get("number","")).startswith("888")), None)
        if not first:
            raise ValueError("No +888 collectible found in listings")

        number = first["number"]
        # price fields (try several keys)
        ton = None
        for key in ("assetPrice","tokenPrice","price"):
            val = first.get(key)
            if isinstance(val, dict) and "value" in val:
                ton = val["value"]
            elif isinstance(val,(int,float,str)):
                ton = val
            if ton:
                break

        usd = first.get("fiatPrice") or first.get("usdPrice") or first.get("priceUsd")
        if not (ton and usd):
            raise ValueError("Incomplete price info in listing")

        # 5) Report back
        await status.delete()
        await message.answer(
            f"💰 Current Floor Number: +{number}\n\n"
            f"• Price: {ton} TON (~${usd})"
        )

    except Exception as e:
        logger.exception("floor error")
        await status.edit_text(f"❌ Failed to fetch floor: {e}")
