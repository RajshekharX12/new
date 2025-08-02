#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  1) Hits the JSON API for sale listings
  2) Falls back to parsing the SSR HTML if JSON fails
  3) Reports the first +888 number’s TON price and USD equivalent
"""

import sys
import logging
import requests
import re
import json
from aiogram.filters import Command
from aiogram.types import Message

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp
bot   = _main.bot

logger = logging.getLogger(__name__)

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
        # --- 1) Try the JSON API endpoint ---
        api_url = "https://fragment.com/api/numbers?filter=sale"
        resp = session.get(api_url, timeout=10)
        if resp.ok and resp.headers.get("Content-Type", "").startswith("application/json"):
            data = resp.json()
            # Expecting a list of listings
            if isinstance(data, list) and data:
                first = data[0]
                number = first.get("number")
                ton    = first.get("assetPrice", {}).get("value") or first.get("tokenPrice") or first.get("price")
                usd    = first.get("fiatPrice") or first.get("usdPrice")
                if number and ton and usd:
                    await status.delete()
                    return await message.answer(
                        f"💰 Current Floor Number: +{number}\n\n"
                        f"• Price: {ton} TON (~${usd})"
                    )
        # --- 2) Fallback to HTML/SSR parse ---
        page_url = "https://fragment.com/numbers?filter=sale"
        page = session.get(page_url, timeout=10)
        page.raise_for_status()
        html_text = page.text
        # look for __NEXT_DATA__
        m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', html_text, re.DOTALL)
        if not m:
            raise ValueError("No SSR data found")
        data = json.loads(m.group(1))
        # recursive search for listing nodes
        def find_list(obj):
            if isinstance(obj, dict):
                # look for an array named "nodes" containing dicts with "number"
                nodes = obj.get("nodes")
                if isinstance(nodes, list) and nodes and isinstance(nodes[0], dict) and "number" in nodes[0]:
                    return nodes
                for v in obj.values():
                    res = find_list(v)
                    if res: return res
            elif isinstance(obj, list):
                for item in obj:
                    res = find_list(item)
                    if res: return res
            return None
        nodes = find_list(data)
        if not nodes:
            raise ValueError("No listings in SSR data")
        first = nodes[0]
        number = first.get("number")
        ton    = (first.get("assetPrice") or {}).get("value") or first.get("tokenPrice") or first.get("price")
        usd    = first.get("fiatPrice") or first.get("usdPrice")
        if not (number and ton and usd):
            raise ValueError("Incomplete price data in SSR")
        await status.delete()
        await message.answer(
            f"💰 Current Floor Number: +{number}\n\n"
            f"• Price: {ton} TON (~${usd})"
        )

    except Exception as e:
        logger.exception("floor error")
        await status.edit_text(f"❌ Failed to fetch floor: {e}")
