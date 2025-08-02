#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  1) Try JSON API (/api/numbers?filter=sale)
  2) Fallback to desktop HTML (/numbers?filter=sale)
  3) Fallback to mobile HTML (m.fragment.com/numbers?filter=sale)
  4) Extract first +888 listing’s TON & USD via regex
"""

import re
import logging
import requests

from aiogram.filters import Command
from aiogram.types import Message
from html import escape

# grab dispatcher & bot from main
import sys
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

def extract_from_json(data):
    nodes = data.get("nodes") or data.get("data") or []
    for n in nodes:
        num = str(n.get("number",""))
        if num.startswith("888"):
            ton = (n.get("assetPrice") or {}).get("value") or n.get("tokenPrice") or n.get("price")
            usd = n.get("fiatPrice") or n.get("usdPrice") or n.get("priceUsd")
            return num, ton, usd
    return None

def extract_from_html(text):
    m_link = re.search(r'href="(/number/(888\d+)/code)"', text)
    if not m_link:
        return None
    num = m_link.group(2)
    detail = session.get(f"https://fragment.com{m_link.group(1)}", timeout=10).text
    ton_m = re.search(r"([\d,]+)\s*TON\b", detail)
    usd_m = re.search(r"~\s*\$([\d,.,]+)", detail)
    if ton_m and usd_m:
        return num, ton_m.group(1).replace(",", ""), usd_m.group(1).replace(",", "")
    return None

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        # 1) JSON API
        api_url = "https://fragment.com/api/numbers?filter=sale"
        r = session.get(api_url, timeout=10)
        if r.ok:
            js = r.json() or {}
            res = extract_from_json(js)
            if res:
                number, ton, usd = res
                await status.delete()
                return await message.answer(f"💰 +{number}: {ton} TON (~${usd})")

        # 2) Desktop HTML
        r = session.get("https://fragment.com/numbers?filter=sale", timeout=10)
        if r.ok:
            res = extract_from_html(r.text)
            if res:
                number, ton, usd = res
                await status.delete()
                return await message.answer(f"💰 +{number}: {ton} TON (~${usd})")

        # 3) Mobile HTML fallback
        r = session.get("https://m.fragment.com/numbers?filter=sale", timeout=10)
        if r.ok:
            res = extract_from_html(r.text)
            if res:
                number, ton, usd = res
                await status.delete()
                return await message.answer(f"💰 +{number}: {ton} TON (~${usd})")

        # all failed
        raise ValueError("No +888 listing found via JSON or HTML")

    except Exception as e:
        logger.exception("floor error")
        msg = escape(str(e))
        await status.edit_text(f"❌ Failed to fetch floor:\n```{msg}```", parse_mode="Markdown")
