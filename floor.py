#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Uses Selenium headless Chrome to load fragment.com
  • Waits for the JS-rendered listing to appear
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
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp
bot   = _main.bot

logger = logging.getLogger(__name__)

def scrape_floor():
    # Setup headless Chrome
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)

    try:
        # 1) Load the sale listings page
        driver.get("https://fragment.com/numbers?filter=sale")

        # 2) Wait for the first +888 link to appear
        wait = WebDriverWait(driver, 15)
        elem = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href^='/number/888'][href$='/code']"))
        )
        href = elem.get_attribute("href")  # full URL
        number = "+" + href.rstrip("/code").split("/")[-1]

        # 3) Navigate to the detail page
        driver.get(href)

        # 4) Wait for price text to render
        wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'TON')]")))

        html = driver.page_source

        # 5) Parse TON and USD via regex
        ton_m = re.search(r"([\d,]+)\s*TON", html)
        usd_m = re.search(r"~\s*\$([\d,.,]+)", html)
        if not ton_m or not usd_m:
            raise RuntimeError("Price information not found on detail page")

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
        await status.edit_text(f"🗑️ Failed to fetch floor: {e}")
