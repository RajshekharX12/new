import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

def get_floor_price():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument('--window-size=1920,1080')
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
    result = "❌ Failed to fetch floor price."
    try:
        driver.get("https://fragment.com/numbers?filter=sale")
        time.sleep(3)  # Wait for JS

        # Find the first number's link
        first_link = driver.find_element("xpath", '//a[contains(@href,"/number/888")]')
        href = first_link.get_attribute('href')

        driver.get(href)
        time.sleep(2)

        ton_elem = driver.find_element("xpath", "//span[contains(text(), 'TON')]")
        usd_elem = driver.find_element("xpath", "//span[contains(text(), '$')]")
        ton = ton_elem.text
        usd = usd_elem.text

        number = href.split('/')[-1]
        result = f"Floor: +{number}\nPrice: {ton} ({usd})\n[Link]({href})"
    except Exception as e:
        result = f"❌ Error: {e}"
    finally:
        driver.quit()
    return result

def floor_command(update: Update, context: CallbackContext):
    update.message.reply_text("Fetching floor price, please wait…")
    floor = get_floor_price()
    update.message.reply_markdown(floor, disable_web_page_preview=True)

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("floor", floor_command))
    updater.start_polling()
    print("Bot started.")
    updater.idle()

if __name__ == "__main__":
    main()
