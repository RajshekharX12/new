import os
import logging
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from safoneapi import SafoneAPI, errors as safone_errors

# Load your Telegram token from .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN in .env")

# Basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot, dispatcher, and Safone client
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
api = SafoneAPI()

@dp.message(Command(commands=["start", "help"]))
async def cmd_start(message: types.Message):
    await message.reply("👋 Hi! Send me any text and I'll reply via SafoneAPI.")

@dp.message()
async def echo_via_safone(message: types.Message):
    text = message.text.strip()
    if not text:
        return
    try:
        reply = api.chat(text)
    except safone_errors.TimeoutError:
        logger.warning("SafoneAPI timeout for: %s", text)
        reply = "⚠️ Request timed out. Please try again."
    except Exception:
        logger.exception("SafoneAPI error")
        reply = "❌ An error occurred. Please try again later."
    await message.answer(reply)

async def main():
    # Starts long-polling
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
