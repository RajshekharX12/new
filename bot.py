
---

**5. `bot.py`**  
```python
import os
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor, types
from safoneapi import SafoneAPI, errors as safone_errors

# Load .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SAFONE_API_KEY = os.getenv("SAFONE_API_KEY")
if not BOT_TOKEN or not SAFONE_API_KEY:
    raise RuntimeError("Missing BOT_TOKEN or SAFONE_API_KEY in .env")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot init
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
api = SafoneAPI(SAFONE_API_KEY)

@dp.message_handler(commands=["start", "help"])
async def send_welcome(message: types.Message):
    await message.reply(
        "👋 Hi! Send me any text and I'll reply via SafoneAPI."
    )

@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_text(message: types.Message):
    user_text = message.text.strip()
    if not user_text:
        return
    try:
        reply = api.chat(user_text)
    except safone_errors.TimeoutError:
        logger.warning("Timeout: %s", user_text)
        reply = "⚠️ Request timed out. Please try again."
    except Exception:
        logger.exception("SafoneAPI error")
        reply = "❌ An error occurred. Please try again later."
    await message.answer(reply)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
