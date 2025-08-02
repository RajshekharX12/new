import os
import logging
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from SafoneAPI import SafoneAPI

# Load .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN in .env")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
api = SafoneAPI()  # no key needed

@dp.message(Command(commands=["start", "help"]))
async def cmd_start(message: types.Message):
    await message.reply("👋 Hi! Send me any text and I'll reply via SafoneAPI.")

@dp.message()
async def handle_text(message: types.Message):
    text = message.text.strip()
    if not text:
        return
    try:
        # call the async SafoneAPI method
        reply = await api.chat(text)
    except Exception as e:
        logger.exception("SafoneAPI error")
        reply = "❌ An error occurred. Please try again later."
    await message.answer(reply)

async def main():
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
