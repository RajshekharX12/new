#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Uses Selenium headless Chrome to load the MarketApp collection page
  • Waits for the “Floor” label in the DOM
  • Extracts the TON and USD prices from its container
  • Replies with "+888 floor: <TON> TON (~$<USD>)"
"""

import sys
import logging
import asyncio

from aiogram.filters import Command
from aiogram.types import Message

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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

    driver = webdriver.Chrome(
        ChromeDriverManager().install(),
        options=options
    )
    wait = WebDriverWait(driver, 15)
    try:
        url = (
            "https://marketapp.ws/collection/"
            "EQAOQdwdw8kGftJCSFgOErM1mBjYPe4DBPq8-AhF6vr9si5N/"
        )
        driver.get(url)

        # 1) Wait for the “Floor” label
        floor_label = wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[text()='Floor']"))
        )
        floor_container = floor_label.find_element(By.XPATH, "..")

        # 2) Pull out the three lines: label, TON, USD
        lines = floor_container.text.strip().split("\n")
        # lines[0] == "Floor", lines[1] == "707 TON", lines[2] == "~$2,534"
        if len(lines) < 3:
            raise RuntimeError("Unexpected layout: floor container text lines < 3")

        ton_text = lines[1].split()[0]     # "707"
        usd_text = lines[2].lstrip("~$")   # "2,534"

        return ton_text, usd_text

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
