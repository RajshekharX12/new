#!/usr/bin/env python3
import os
import html
import logging

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode

from SafoneAPI import SafoneAPI

# ─── LOAD ENV ────────────────────────────────────────────────────
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")

# ─── LOGGING ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ─── BOT & DISPATCHER ────────────────────────────────────────────
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp  = Dispatcher()

# ─── SAFONEAPI CLIENT ─────────────────────────────────────────────
api = SafoneAPI()

# ─── PLUGINS & HANDLERS ──────────────────────────────────────────
# Inline fragment links, speedtest, code review, floor price, update
import fragment_url   # inline 888 → fragment.com URL
import speed          # /speed VPS speedtest
import review         # /review code quality + /help
import floor          # /888 current floor price
import update         # /update auto-pull & summary

# ─── CHATGPT FALLBACK ─────────────────────────────────────────────
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

# ─── RUN BOT ─────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("🚀 Bot is starting…")
    dp.run_polling(bot)
