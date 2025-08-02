#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Uses Playwright headless Chromium
  • Waits for network idle
  • Extracts all links, filters the first +888 link
  • Fetches its detail page, parses TON and USD price
"""

import sys
import logging
import asyncio
import re

from aiogram.filters import Command
from aiogram.types import Message
from playwright.async_api import async_playwright

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)

async def fetch_floor():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        # 1) Navigate and wait for network idle
        await page.goto("https://fragment.com/numbers?filter=sale", wait_until="networkidle")
        # 2) Evaluate all <a> hrefs on the page
        hrefs = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.href)"
        )
        # 3) Find the first matching +888 listing
        candidate = next(
            (h for h in hrefs if "/number/888" in h and h.rstrip("/").endswith("/code")),
            None
        )
        if not candidate:
            await browser.close()
            raise ValueError("No +888 listing link found")
        number = "+" + candidate.rstrip("/").split("/")[-2]

        # 4) Navigate to detail page
        await page.goto(candidate, wait_until="networkidle")
        content = await page.content()
        await browser.close()

    # 5) Regex extract prices
    m_ton = re.search(r"([\d,]+)\s*TON\b", content)
    m_usd = re.search(r"~\s*\$([\d,.,]+)", content)
    if not m_ton or not m_usd:
        raise ValueError("Could not parse price information")
    ton = m_ton.group(1).replace(",", "")
    usd = m_usd.group(1).replace(",", "")
    return number, ton, usd

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        number, ton, usd = await fetch_floor()
        await status.delete()
        await message.answer(f"💰 {number}: {ton} TON (~${usd})")
    except Exception as e:
        logger.exception("floor error")
        from html import escape
        safe = escape(str(e))
        await status.edit_text(
            f"❌ Failed to fetch floor:\n```{safe}```",
            parse_mode="Markdown"
        )
