#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Uses Playwright headless Chromium to load fragment.com fully
  • Finds the first +888 listing
  • Extracts its TON price & USD equivalent
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
        await page.goto("https://fragment.com/numbers?filter=sale", wait_until="domcontentloaded")
        await page.wait_for_selector("a[href^='/number/888'][href$='/code']", timeout=15000)
        href = await page.eval_on_selector("a[href^='/number/888'][href$='/code']", "el => el.href")
        number = "+" + href.rstrip("/code").split("/")[-1]
        await page.goto(href, wait_until="domcontentloaded")
        await page.wait_for_selector("text=/\\d+\\s*TON/", timeout=15000)
        content = await page.content()
        await browser.close()

    ton_m = re.search(r"([\d,]+)\s*TON", content)
    usd_m = re.search(r"~\s*\$([\d,.,]+)", content)
    if not ton_m or not usd_m:
        raise ValueError("Price info not found")
    ton = ton_m.group(1).replace(",", "")
    usd = usd_m.group(1).replace(",", "")
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
