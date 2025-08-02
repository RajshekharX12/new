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
import update         # /update: auto-pull, summary & hot-restart
import review         # /review code quality + /help

# ─── SAFONEAPI CLIENT ──────────────────────────────────────────
api = SafoneAPI()

# ─── /start HANDLER ────────────────────────────────────────────
@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "👋 Welcome! I can help you with:\n"
        "• /speed  — run a VPS speed test 🌐\n"
        "• /update — pull latest code, report changes & restart 🔄\n"
        "• /review — code quality review 📋\n"
        "• /help   — list commands ❓\n\n"
        "✉️ Send any other text and I'll reply via ChatGPT ✨"
    )

# ─── CHATGPT FALLBACK ──────────────────────────────────────────
@dp.message(F.text & ~F.text.startswith("/"))
async def chatgpt_handler(message: types.Message):
    text = message.text.strip()
    if not text:
        return
    try:
        resp = await api.chatgpt(text)
        answer = getattr(resp, "message", None) or str(resp)
        await message.answer(html.escape(answer))
    except Exception:
        logger.exception("chatgpt error")
        await message.reply("🚨 Error: SafoneAPI failed or no response.")

# ─── RUN BOT ───────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("🚀 Bot is starting…")
    dp.run_polling(bot)
