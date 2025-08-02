#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Loads fragment.com/numbers?filter=sale
  • Extracts Next.js buildId from __NEXT_DATA__
  • GETs the JSON data at /_next/data/{buildId}/numbers.json?filter=sale
  • Finds the first +888 number and reports its TON & USD price
"""

import sys
import re
import json
import logging
import requests

from aiogram.filters import Command
from aiogram.types import Message
from html import escape

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)
session = requests.Session()
session.headers.update({"User-Agent":"Mozilla/5.0"})

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        # 1) Get the sale page to grab buildId
        url = "https://fragment.com/numbers?filter=sale"
        r = session.get(url, timeout=10)
        r.raise_for_status()
        html = r.text

        # 2) Extract the __NEXT_DATA__ JSON blob
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', html, re.DOTALL)
        if not m:
            raise ValueError("Could not find Next.js data on page")
        nd = json.loads(m.group(1))

        # 3) Pull out the buildId
        build_id = nd.get("buildId") or (nd.get("props",{})
                                         .get("buildId"))
        if not build_id:
            raise ValueError("Could not find buildId in Next.js data")

        # 4) Fetch the JSON data directly
        json_url = f"https://fragment.com/_next/data/{build_id}/numbers.json?filter=sale"
        jr = session.get(json_url, timeout=10)
        jr.raise_for_status()
        data = jr.json()

        # 5) Find the listings array in this JSON
        #    Next.js props path: data["pageProps"]["numbers"]["nodes"]
        nodes = (data.get("pageProps",{})
                     .get("numbers",{})
                     .get("nodes",[]))
        if not nodes:
            raise ValueError("No sale listings in JSON data")

        # 6) Find first number starting with 888
        first = next((n for n in nodes if str(n.get("number","")).startswith("888")), None)
        if not first:
            raise ValueError("No +888 collectible found")

        # 7) Extract prices
        number = first["number"]
        ton = (first.get("assetPrice") or {}).get("value") or first.get("tokenPrice") or first.get("price")
        usd = first.get("fiatPrice") or first.get("usdPrice") or first.get("priceUsd")
        if ton is None or usd is None:
            raise ValueError("Incomplete price info in JSON")

        # 8) Send result
        await status.delete()
        await message.answer(f"💰 +{number}: {ton} TON (~${usd})")

    except Exception as e:
        logger.exception("floor error")
        msg = escape(str(e))
        await status.edit_text(f"❌ Failed to fetch floor:\n```{msg}```", parse_mode="Markdown")
