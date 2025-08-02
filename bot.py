import os
import logging
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from SafoneAPI import SafoneAPI

# Load your Telegram token
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN in .env")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Telegram bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Initialize SafoneAPI client (no API key needed)
api = SafoneAPI()

@dp.message(Command(commands=["start", "help"]))
async def cmd_start(message: types.Message):
    await message.reply(
        "👋 Hi there! Send me any text and I'll relay it through SafoneAPI."
    )

@dp.message()
async def forward_to_safone(message: types.Message):
    text = message.text.strip()
    if not text:
        return

    try:
        # Use the generic chatbot endpoint
        reply = await api.chatbot(text)
    except AttributeError:
        # Fallback: show you exactly which methods exist
        methods = [m for m in dir(api) if callable(getattr(api, m)) and not m.startswith("_")]
        await message.reply("⚠️ `.chatbot()` not found. Available methods:\n" + ", ".join(methods))
        return
    except Exception as e:
        logger.exception("SafoneAPI error")
        await message.reply(f"❌ SafoneAPI Error:\n{e}")
        return

    await message.answer(reply)

async def main():
    # Start long-polling
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
