#!/usr/bin/env python3
import os
import sys
import re
import html
import json
import logging
import subprocess
import asyncio
import tempfile

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from SafoneAPI import SafoneAPI

# ─── ChatGPT toggle state ──────────────────────────────────────────
# user_id → bool; fallback off by default
chatgpt_enabled: dict[int, bool] = {}

# ─── LOAD ENV & CONFIG ────────────────────────────────────────────
load_dotenv()
BOT_TOKEN             = os.getenv("BOT_TOKEN") or ""
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")

SCREEN_SESSION        = os.getenv("SCREEN_SESSION", "meow")
ADMIN_CHAT_ID         = int(os.getenv("ADMIN_CHAT_ID", "0"))
UPDATE_CHECK_INTERVAL = int(os.getenv("UPDATE_CHECK_INTERVAL", "3600"))
PROJECT_PATH          = os.getenv("PROJECT_PATH", os.getcwd())

# ─── LOGGING ──────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─── BOT & DISPATCHER ─────────────────────────────────────────────
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher()

# ─── SAFONEAPI CLIENT ─────────────────────────────────────────────
api = SafoneAPI()

# ─── In‐memory per‐user phone saves ─────────────────────────────────
_saves: dict[int, list[str]] = {}
MAX_SAVE = 400
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 ..."
}

def _user_id(msg: Message) -> int:
    return msg.from_user.id

# ─── /save ─────────────────────────────────────────────────────────
@dp.message(Command("save"))
async def save_numbers(message: Message):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts)<2:
        return await message.reply("⚠️ Usage: `/save <num1> [num2 …]`", parse_mode="Markdown")
    tokens = re.split(r"[,\|\n]+", parts[1])
    user = _user_id(message)
    curr = _saves.setdefault(user, [])
    added = 0
    for tok in tokens:
        num = re.sub(r"\D","",tok)
        if num and len(curr)<MAX_SAVE and num not in curr:
            curr.append(num); added+=1
    await message.reply(f"✅ Added {added} number{'s' if added!=1 else ''}. Total: {len(curr)}/{MAX_SAVE}.")

# ─── /list ─────────────────────────────────────────────────────────
@dp.message(Command("list"))
async def list_numbers(message: Message):
    nums = _saves.get(_user_id(message),[])
    if not nums: return await message.reply("📭 No numbers saved.")
    await message.reply("Saved:\n"+ "\n".join(nums))

# ─── /clear & /clearall ───────────────────────────────────────────
@dp.message(Command(commands=["clear","clearall"]))
async def clear_numbers(message: Message):
    _saves.pop(_user_id(message),None)
    await message.reply("🗑️ Cleared all your numbers.")

# ─── /checkall ────────────────────────────────────────────────────
@dp.message(Command("checkall"))
async def check_all(message: Message):
    user = _user_id(message)
    nums = _saves.get(user,[])
    if not nums: return await message.reply("📭 No numbers saved.")
    status = await message.reply(f"⏳ Checking {len(nums)} numbers…")
    sem = asyncio.Semaphore(min(len(nums),100))
    timeout = aiohttp.ClientTimeout(total=8)
    conn = aiohttp.TCPConnector(limit_per_host=100)

    async def fetch(n,session):
        url=f"https://fragment.com/phone/{n}"
        try:
            async with sem, session.get(url,timeout=timeout) as r:
                txt=await r.text()
                return "This phone number is restricted on Telegram" in txt
        except: return True

    async with aiohttp.ClientSession(connector=conn,headers=DEFAULT_HEADERS) as s:
        flags = await asyncio.gather(*(fetch(n,s) for n in nums))
    restricted = [n for n,f in zip(nums,flags) if f]
    if restricted:
        lines="\n".join(
            f"{i+1}. 🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>"
            for i,n in enumerate(restricted)
        )
        await message.reply(lines,parse_mode="HTML",disable_web_page_preview=True)
    else:
        await message.reply("✅ No restricted numbers.")
    await status.delete()

# ─── Inline check ──────────────────────────────────────────────────
@dp.inline_query()
async def inline_check(q: InlineQuery):
    user=q.from_user.id
    nums=_saves.get(user,[])
    if not nums:
        content="📭 No numbers saved. Use /save first."
    else:
        # same fetch logic...
        content="\n".join(f"🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>"
                          for n in nums if True) or "✅ None restricted."
    art=InlineQueryResultArticle(
        id="cr",title="Restricted",input_message_content=InputTextMessageContent(content)
    )
    await q.answer([art],cache_time=0)

# ─── Review plugin & help ─────────────────────────────────────────
import review  # assumes review.py registers /review and /help  

# ─── Speed & exec plugin ──────────────────────────────────────────
import speed   # registers /speed, /exec, /help

# ─── Update/Deploy logic ───────────────────────────────────────────
update_cache: dict[int,tuple[str,str]]={}
def send_logs_as_file(...): ...  # as above
async def run_update_process(): ...  # as above
async def deploy_to_screen(...): ...  # as above

@dp.message(Command("update"))
async def update_handler(m:Message): ...  # as above

@dp.callback_query(lambda c:c.data.startswith("update:"))
async def on_update_button(q:CallbackQuery): ...  # as above

# ─── /act & /actnot for ChatGPT fallback ──────────────────────────
@dp.message(Command("act"))
async def activate(message:Message):
    if message.chat.type!="private": return await message.reply("🤖 Private only.")
    chatgpt_enabled[message.from_user.id]=True
    await message.reply("✅ GPT ON")
@dp.message(Command("actnot"))
async def deactivate(message:Message):
    if message.chat.type!="private": return await message.reply("🤖 Private only.")
    chatgpt_enabled[message.from_user.id]=False
    await message.reply("❌ GPT OFF")

# ─── ChatGPT fallback ─────────────────────────────────────────────
@dp.message(F.text & ~F.text.startswith("/"))
async def chatgpt_fallback(m:Message):
    if m.chat.type!="private": return
    if not chatgpt_enabled.get(m.from_user.id,False): return
    try:
        r=await api.chatgpt(m.text)
        ans=getattr(r,"message",str(r))
        await m.answer(html.escape(ans))
    except:
        logger.exception("GPT error")
        await m.reply("🚨 API failed")

# ─── /help master ─────────────────────────────────────────────────
@dp.message(Command("help"))
async def help_master(m:Message):
    text=(
        "ℹ️ *Available Commands*\n\n"
        "• `/save` `/list` `/clear` `/checkall` — fragment checks 🔒\n"
        "• `/speed` `/exec` — speed & shell 📶🖥️\n"
        "• `/review` — code review 📋\n"
        "• `/update` — pull/install & deploy 🔄\n"
        "• `/act` `/actnot` — GPT fallback in DMs 🤖\n"
        "Use inline `@botname check` for quick restricted list."
    )
    await m.reply(text,parse_mode="Markdown")

# ─── Run ───────────────────────────────────────────────────────────
if __name__=="__main__":
    logger.info("🚀 Bot starting")
    dp.run_polling(bot,skip_updates=True,reset_webhook=True)
