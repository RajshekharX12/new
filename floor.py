#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Uses Selenium + headless Chrome to load Fragment’s sale page
  • Finds the first +888 number link
  • Navigates there and extracts TON & USD prices
  • Replies with "+888 floor: <TON> TON (~$<USD>)"
"""

import sys
import logging
import time
import asyncio

from aiogram.filters import Command
from aiogram.types import Message

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# webdriver-manager to auto-install chromedriver
from webdriver_manager.chrome import ChromeDriverManager

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)

def scrape_floor():
    """Blocking Selenium function to fetch the floor price."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")

    # Auto-install chromedriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # Step 1: load the sale listings
        driver.get("https://fragment.com/numbers?filter=sale")
        time.sleep(5)  # allow JS to run

        # Step 2: find & click the first +888 link
        link = driver.find_element(By.CSS_SELECTOR, 'a[href^="/number/888"]')
        href = link.get_attribute("href")
        driver.get(href)
        time.sleep(5)  # allow detail page JS to run

        # Step 3: scrape the prices
        # 👉 You may need to adjust these selectors if the site updates!
        ton_text = driver.find_element(By.CSS_SELECTOR, ".sc-eCImvq.hOEfDz").text  # e.g. "733 TON"
        usd_text = driver.find_element(By.CSS_SELECTOR, ".sc-hXhQae.hqwNId").text  # e.g. "~ $2,634"

        # clean up
        ton = ton_text.split()[0].replace(",", "")
        usd = usd_text.strip("~ $").replace(",", "")
        return ton, usd

    finally:
        driver.quit()

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        loop = asyncio.get_event_loop()
        ton, usd = await loop.run_in_executor(None, scrape_floor)
        await status.delete()
        await message.answer(f"💰 +888 floor: {ton} TON (~${usd})")
    except Exception as e:
        logger.exception("floor error")
        from html import escape
        safe = escape(str(e))
        await status.edit_text(
            f"❌ Failed to fetch floor:\n```{safe}```",
            parse_mode="Markdown"
        )
