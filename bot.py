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

# ─── PLUGINS ──────────────────────────────────────────────────
import fragment_url   # inline 888 → fragment.com
import speed          # /speed VPS speedtest
import update         # /update auto-pull & summary

# ─── SAFONEAPI CLIENT ──────────────────────────────────────────
api = SafoneAPI()

# ─── /start HANDLER ────────────────────────────────────────────
@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "👋 Welcome! Send me any text and I'll reply via SafoneAPI.\n"
        "• /speed – run a VPS speed test\n"
        "• /update – pull latest code and report changes"
    )

# ─── CHATGPT FALLBACK ──────────────────────────────────────────
@dp.message(F.text & ~F.text.startswith("/"))
async def chatgpt_handler(message: types.Message):
    text = message.text.strip()
    if not text:
        return

    try:
        response = await api.chatgpt(text)
        answer = getattr(response, "message", None) or str(response)
        await message.answer(html.escape(answer))
    except Exception:
        logger.exception("Error in chatgpt handler")
        await message.reply("🚨 Error: SafoneAPI failed or no response.")

# ─── RUN BOT ───────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("🚀 Bot is starting…")
    dp.run_polling(bot)
