#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Uses Selenium headless Chrome to load fragment.com
  • Finds the first '/number/888…/code' link
  • Navigates there and extracts TON price & USD equivalent
"""

import sys
import re
import logging
import asyncio

from aiogram.filters import Command
from aiogram.types import Message

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp
bot   = _main.bot

logger = logging.getLogger(__name__)

def scrape_floor():
    # setup headless Chrome
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)

    try:
        # 1) Load the sale listings page
        driver.get("https://fragment.com/numbers?filter=sale")
        # 2) Find first +888 link
        elems = driver.find_elements("xpath", "//a[starts-with(@href,'/number/888') and contains(@href,'/code')]")
        if not elems:
            raise RuntimeError("No +888 listings found")
        href = elems[0].get_attribute("href")
        number = "+" + href.rstrip("/code").split("/")[-1]

        # 3) Navigate to detail page
        driver.get(href)
        html = driver.page_source

        # 4) Extract TON and USD via regex
        ton_m = re.search(r"([\d,]+)\s*TON", html)
        usd_m = re.search(r"~\s*\$([\d,.,]+)", html)
        if not ton_m or not usd_m:
            raise RuntimeError("Price info not found")
        ton = ton_m.group(1).replace(",", "")
        usd = usd_m.group(1).replace(",", "")

        return number, ton, usd
    finally:
        driver.quit()

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        loop = asyncio.get_event_loop()
        number, ton, usd = await loop.run_in_executor(None, scrape_floor)
        await status.delete()
        await message.answer(
            f"💰 Current Floor Number: {number}\n\n"
            f"• Price: {ton} TON (~${usd})"
        )
    except Exception as e:
        logger.exception("floor error")
        await status.edit_text(f"❌ Failed to fetch floor: {e}")
