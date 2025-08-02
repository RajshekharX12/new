import os
import html
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties

from SafoneAPI import SafoneAPI

# ─── LOAD ENV ─────────────────────────────────────────────────
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")

# ─── LOGGING ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ─── BOT & DISPATCHER ──────────────────────────────────────────
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ─── INLINE FRAGMENT HANDLER ──────────────────────────────────
# this will register the @dp.inline_query handler from fragment_url.py
import fragment_url

# ─── SAFONE CLIENT ─────────────────────────────────────────────
api = SafoneAPI()

# ─── /start HANDLER ────────────────────────────────────────────
@dp.message(CommandStart())
async def start(message: types.Message):
    # Escape <sawal> so HTML parser won’t choke
    await message.answer(
        "👋 Bhai, mujhe 'bhai &lt;sawal&gt;' likh kar puchho. Main Hindi mein dost jaisa reply dunga!"
    )

# ─── “bhai” HANDLER ─────────────────────────────────────────────
@dp.message(F.text.startswith("bhai"))
async def chatgpt_handler(message: types.Message):
    try:
        parts = message.text.split(maxsplit=1)
        query = parts[1] if len(parts) > 1 else None
        if not query and message.reply_to_message:
            query = message.reply_to_message.text
        if not query:
            return await message.reply("❗ Bhai, mujhe question toh de...")

        if len(query) > 1000:
            return await message.reply("⚠️ Bhai, question zyada lamba ho gaya. Thoda chhota puchho.")

        status = await message.reply("🧠 Generating answer...")

        prompt_intro = (
            "You are user's friend. Reply in friendly Hindi with emojis, "
            "using 'bhai' style words like 'Arey bhai', 'Nahi bhai', etc.\n\n"
        )
        full_prompt = prompt_intro + query

        response = await api.chatgpt(full_prompt)
        answer = getattr(response, "message", None)
        if not answer:
            raise ValueError("Invalid response from API")

        safe_answer = html.escape(answer)
        formatted = (
            f"<b>Query:</b>\n"
            f"~ <i>{html.escape(query)}</i>\n\n"
            f"<b>ChatGPT:</b>\n"
            f"~ <i>{safe_answer}</i>"
        )
        await status.edit_text(formatted)

    except Exception:
        logger.exception("Unexpected error")
        await message.reply("🚨 Error: Safone API failed ya response nahi aaya.")

# ─── RUN BOT ───────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("🚀 Bot is starting...")
    dp.run_polling(bot)
