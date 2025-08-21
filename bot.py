#!/usr/bin/env python3
import os
import sys
import html
import json
import logging
import asyncio

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message

from SafoneAPI import SafoneAPI

# ─── ChatGPT toggle state ──────────────────────────────────────────
# Maps user_id → bool (True if ChatGPT fallback is enabled in DMs)
chatgpt_enabled: dict[int, bool] = {}

# ─── LOAD ENV & CONFIG ────────────────────────────────────────────
load_dotenv()
BOT_TOKEN       = os.getenv("BOT_TOKEN") or ""
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")

SCREEN_SESSION  = os.getenv("SCREEN_SESSION", "meow")   # kept for compatibility with other plugins
ADMIN_CHAT_ID   = int(os.getenv("ADMIN_CHAT_ID", "0"))
PROJECT_PATH    = os.getenv("PROJECT_PATH", os.getcwd())

# Memory settings
MEMORY_FILE     = os.getenv("MEMORY_FILE", "memory.json")
MAX_MEMORY      = int(os.getenv("MAX_MEMORY", "20"))  # messages kept per chat

# ─── LOGGING ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ─── BOT & DISPATCHER ─────────────────────────────────────────────
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ─── SAFONEAPI CLIENT ─────────────────────────────────────────────
api = SafoneAPI()

# ─── PLUGINS (unchanged) ──────────────────────────────────────────
import fragment_url   # inline 888 → fragment.com URL
import speed          # /speed VPS speedtest
import review         # /review code quality + /help
import fragment       # /save, /list, /checkall, inline /check handlers

# ─── SIMPLE PERSISTENT MEMORY (per chat) ──────────────────────────
_memory: dict[str, list[dict]] = {}  # key: str(chat_id), value: [{"role":"user|assistant","content":str}, ...]

def _load_memory():
    global _memory
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            _memory = json.load(f)
    except Exception:
        _memory = {}

def _save_memory():
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(_memory, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed saving memory: {e}")

def _append_memory(chat_id: int, role: str, content: str):
    key = str(chat_id)
    _memory.setdefault(key, [])
    _memory[key].append({"role": role, "content": (content or "").strip()})
    # trim
    if len(_memory[key]) > MAX_MEMORY:
        _memory[key] = _memory[key][-MAX_MEMORY:]
    _save_memory()

def _build_context(chat_id: int, user_text: str) -> str:
    """Build a single prompt string with short context so SafoneAPI can 'remember'."""
    msgs = _memory.get(str(chat_id), [])[-(MAX_MEMORY - 1):]
    ctx_lines = []
    for m in msgs:
        r = m.get("role", "user")
        c = (m.get("content", "") or "").replace("\n", " ").strip()
        if not c:
            continue
        ctx_lines.append(f"{r.title()}: {c}")
    ctx = "\n".join(ctx_lines)

    guidelines = (
        "Guidelines: Reply briefly, be friendly, and sprinkle a few relevant emojis naturally. "
        "If the user asks for code or commands, give them clean and minimal. Avoid markdown headings like '##'; "
        "prefer clear lines with emojis instead."
    )

    prefix = f"Previous conversation:\n{ctx}\n\n" if ctx else ""
    prompt = f"{prefix}User: {user_text}\n\n{guidelines}"
    return prompt

def _emojify(text: str) -> str:
    """Make responses feel more lively with emojis and convert '##' style headers to emoji bullets."""
    text = text or ""
    lines = text.splitlines()
    out = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("##"):
            # turn markdown heading into emoji bullet
            s = "✨ " + s.lstrip("#").strip()
        elif s.startswith("* ") or s.startswith("- "):
            s = "• " + s[2:].strip() + " 🔹"
        out.append(s)
    result = "\n".join(out).strip()

    # If there are zero emojis at all, add a soft footer emoji.
    if not any(ch in result for ch in "😀😁😂🤣😊😍😘😎🤔🙌👍🔥✨💡✅⚡️🎯💻📌📎🛠️🧠🔧🔗📝🔒🚀"):
        result = (result + "\n\n✨").strip()
    return result

# ─── /act & /actnot Commands (unchanged behavior for DMs) ─────────
@dp.message(Command("act"))
async def activate_chatgpt(message: Message):
    if message.chat.type != "private":
        return await message.reply("🤖 /act only works in a private chat.")
    uid = message.from_user.id
    chatgpt_enabled[uid] = True
    await message.reply("✅ ChatGPT fallback is now ON for your DMs.")

@dp.message(Command("actnot"))
async def deactivate_chatgpt(message: Message):
    if message.chat.type != "private":
        return await message.reply("🤖 /actnot only works in a private chat.")
    uid = message.from_user.id
    chatgpt_enabled[uid] = False
    await message.reply("❌ ChatGPT fallback is now OFF for your DMs.")

# ─── ChatGPT Fallback (DMs) with memory + emojis ──────────────────
@dp.message(F.text & ~F.text.startswith("/"))
async def chatgpt_handler(message: Message):
    # only in private when /act has been used
    if message.chat.type != "private":
        return
    if not chatgpt_enabled.get(message.from_user.id, False):
        return

    text = (message.text or "").strip()
    if not text:
        return

    try:
        _append_memory(message.chat.id, "user", text)
        prompt = _build_context(message.chat.id, text)
        resp   = await api.chatgpt(prompt)
        answer = getattr(resp, "message", None) or str(resp)
        answer = _emojify(answer)
        _append_memory(message.chat.id, "assistant", answer)
        await message.answer(html.escape(answer))
    except Exception:
        logger.exception("chatgpt error")
        await message.reply("🚨 SafoneAPI failed or no response.")

# ─── Group/Supergroup handler: mention-or-reply to talk ───────────
BOT_USERNAME = None
BOT_ID = None

def _is_addressed_to_bot(msg: Message) -> bool:
    try:
        if msg.chat.type not in ("group", "supergroup"):
            return False
        text = (msg.text or "")
        mentioned = False
        if BOT_USERNAME and ("@" + BOT_USERNAME.lower()) in text.lower():
            mentioned = True
        replied = bool(msg.reply_to_message and msg.reply_to_message.from_user and msg.reply_to_message.from_user.id == BOT_ID)
        # also allow a simple prefix "!"
        prefixed = text.strip().startswith("!")
        return mentioned or replied or prefixed
    except Exception:
        return False

def _strip_bot_mention(text: str) -> str:
    if not text:
        return text
    if BOT_USERNAME:
        text = text.replace(f"@{BOT_USERNAME}", "", 1)
        text = text.replace(f"@{BOT_USERNAME.lower()}", "", 1)
    if text.strip().startswith("!"):
        text = text.strip()[1:].lstrip()
    return text.strip()

@dp.message(F.text & ((F.chat.type == "group") | (F.chat.type == "supergroup")))
async def group_chatgpt_handler(message: Message):
    # Lightly remember group chat to build context, even if not directly addressed.
    txt = (message.text or "").strip()
    if txt and len(txt) <= 200:
        _append_memory(message.chat.id, "user", f"[group context] {txt}")

    if not _is_addressed_to_bot(message):
        return

    text = _strip_bot_mention(txt)
    if not text:
        return

    try:
        _append_memory(message.chat.id, "user", text)
        prompt = _build_context(message.chat.id, text)
        resp   = await api.chatgpt(prompt)
        answer = getattr(resp, "message", None) or str(resp)
        answer = _emojify(answer)
        _append_memory(message.chat.id, "assistant", answer)
        await message.reply(html.escape(answer))
    except Exception as e:
        logger.exception(f"group chatgpt error: {e}")
        await message.reply("⚠️ Couldn't get a reply right now.")

# ─── STARTUP ───────────────────────────────────────────────────────
@dp.startup()
async def on_startup():
    global BOT_USERNAME, BOT_ID
    _load_memory()
    me = await bot.get_me()
    BOT_USERNAME = (me.username or "").strip()
    BOT_ID = me.id
    logger.info(f"🤖 @{BOT_USERNAME} (id={BOT_ID}) is up. Memory file: {MEMORY_FILE}")

# ─── RUN ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("🚀 Bot is starting…")
    dp.run_polling(bot, skip_updates=True, reset_webhook=True)
