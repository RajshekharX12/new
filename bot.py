import os
import logging
import asyncio
import json
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

# Init bot + dispatcher + SafoneAPI client
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
api = SafoneAPI()

@dp.message(Command(commands=["start", "help"]))
async def cmd_start(message: types.Message):
    await message.reply("👋 Hi! Send me any text and I'll reply using SafoneAPI.")

@dp.message()
async def forward_to_safone(message: types.Message):
    user_text = message.text.strip()
    if not user_text:
        return

    try:
        # call the async chatbot endpoint
        res = await api.chatbot(user_text)
        # extract the actual reply text
        if isinstance(res, dict):
            content = res.get("bot") or res.get("reply") or res.get("results") or json.dumps(res)
        elif hasattr(res, "bot"):
            content = res.bot
        elif hasattr(res, "reply"):
            content = res.reply
        elif hasattr(res, "results"):
            content = res.results
        else:
            content = str(res)
    except Exception as e:
        logger.exception("SafoneAPI error")
        await message.reply(f"❌ SafoneAPI Error:\n{e}")
        return

    # ensure it's a string
    if not isinstance(content, str):
        content = json.dumps(content)

    await message.answer(content)

async def main():
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
