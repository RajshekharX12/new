#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Uses system Chromium & Chromedriver (installed via apt)
  • Loads Fragment’s sale page and detail page fully
  • Extracts TON and USD prices via Selenium explicit waits
  • Replies with "+888 floor: <TON> TON (~$<USD>)"
"""

import sys
import logging
import asyncio

from aiogram.filters import Command
from aiogram.types import Message

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# grab dispatcher from main
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)

# Constants
SALE_URL          = "https://fragment.com/numbers?filter=sale"
XPATH_FIRST_LINK  = "//a[starts-with(@href, '/number/888') and contains(@href, '/code')]"
XPATH_FLOOR_LABEL = "//div[text()='Floor']"
CHROME_BINARY     = "/usr/bin/chromium-browser"  # or "/usr/bin/chromium"
DRIVER_PATH       = "/usr/bin/chromedriver"

def scrape_floor():
    # 1) Configure headless Chrome
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    service = Service(DRIVER_PATH)
    driver  = webdriver.Chrome(service=service, options=options)
    wait    = WebDriverWait(driver, 15)

    try:
        # 2) Load sale page & wait for first +888 link
        driver.get(SALE_URL)
        first = wait.until(EC.element_to_be_clickable((By.XPATH, XPATH_FIRST_LINK)))
        detail_url = first.get_attribute("href")

        # 3) Load detail page & wait for “Floor” label
        driver.get(detail_url)
        floor_label = wait.until(EC.presence_of_element_located((By.XPATH, XPATH_FLOOR_LABEL)))
        container   = floor_label.find_element(By.XPATH, "..")

        # 4) Parse text lines: [ “Floor”, “707 TON”, “~ $2,534” ]
        lines = container.text.strip().split("\n")
        if len(lines) < 3:
            raise RuntimeError("Unexpected detail layout")

        ton_text = lines[1].split()[0].replace(",", "")
        usd_text = lines[2].lstrip("~ $").replace(",", "")
        number   = detail_url.rstrip("/").split("/")[-2]

        return number, ton_text, usd_text

    finally:
        driver.quit()

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        loop = asyncio.get_event_loop()
        number, ton, usd = await loop.run_in_executor(None, scrape_floor)
        await status.delete()
        await message.answer(f"💰 +{number}: {ton} TON (~${usd})")
    except Exception as e:
        logger.exception("floor error")
        from html import escape
        safe = escape(str(e))
        await status.edit_text(
            f"❌ Failed to fetch floor:\n```{safe}```",
            parse_mode="Markdown"
        )
