#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Uses your provided Selenium snippet verbatim  
  • Opens Fragment’s sale page, waits 5s  
  • Clicks first +888 link, waits 5s  
  • Extracts TON & USD prices via your selectors  
  • Replies with "+888 floor: <TON> TON (~$<USD>)"
"""

import sys
import time
import logging
from aiogram.filters import Command
from aiogram.types import Message

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)

def scrape_floor():
    # exactly your code:
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')

    service = Service('chromedriver')
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get("https://fragment.com/numbers?filter=sale")
        time.sleep(5)

        first_number_link = driver.find_element(By.CSS_SELECTOR, 'a[href^="/number/888"]')
        url = first_number_link.get_attribute('href')

        driver.get(url)
        time.sleep(5)

        ton_price = driver.find_element(By.CSS_SELECTOR, '.sc-eCImvq.hOEfDz').text
        usd_price = driver.find_element(By.CSS_SELECTOR, '.sc-hXhQae.hqwNId').text

        return ton_price.split()[0].replace(",", ""), usd_price.strip("~ $").replace(",", "")

    finally:
        driver.quit()

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        ton, usd = await asyncio.get_event_loop().run_in_executor(None, scrape_floor)
        await status.delete()
        await message.answer(f"💰 +888 floor: {ton} TON (~${usd})")
    except Exception as e:
        logger.exception("floor error")
        from html import escape
        safe = escape(str(e))
        await status.edit_text(f"❌ Failed to fetch floor:\n```{safe}```", parse_mode="Markdown")
