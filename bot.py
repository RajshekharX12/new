import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from SafoneAPI import SafoneAPI, errors

API_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # ← replace with your real token

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher()

    safone = SafoneAPI()

    @dp.message()
    async def handle_message(message: types.Message):
        prompt = message.text
        try:
            resp = await safone.chatgpt(prompt)
            # If the response object has .results, use it; otherwise take resp directly
            answer = getattr(resp, "results", resp)
        except errors.TimeoutError:
            await message.reply("⚠️ SafoneAPI request timed out. Please try again.")
        except Exception as e:
            await message.reply(f"⚠️ Unexpected error: {e}")
        else:
            await message.reply(answer)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

