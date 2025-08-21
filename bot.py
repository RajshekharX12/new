#!/usr/bin/env python3
import os
import sys
import html
import json
import logging
import asyncio
import re
from typing import Dict, List, Tuple, Optional  # ← added Tuple, Optional

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message, InlineQuery, InlineQueryResultArticle, InputTextMessageContent  # ← added inline types

from SafoneAPI import SafoneAPI

# ─── ChatGPT toggle state (DMs) ────────────────────────────────────
chatgpt_enabled: Dict[int, bool] = {}

# ─── LOAD ENV & CONFIG ────────────────────────────────────────────
load_dotenv()
BOT_TOKEN    = os.getenv("BOT_TOKEN") or ""
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")

SCREEN_SESSION = os.getenv("SCREEN_SESSION", "meow")   # kept for compatibility with other plugins
ADMIN_CHAT_ID  = int(os.getenv("ADMIN_CHAT_ID", "0"))
PROJECT_PATH   = os.getenv("PROJECT_PATH", os.getcwd())

# Memory settings
MEMORY_FILE = os.getenv("MEMORY_FILE", "memory.json")
MAX_MEMORY  = int(os.getenv("MAX_MEMORY", "20"))  # messages kept per chat

# ─── LOGGING ──────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─── BOT & DISPATCHER ─────────────────────────────────────────────
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ─── SAFONEAPI CLIENT ─────────────────────────────────────────────
api = SafoneAPI()

# ─── PLUGINS (unchanged) ──────────────────────────────────────────
import fragment_url   # inline 888 → fragment.com URL
import speed          # /speed VPS speedtest
import fragment       # /save, /list, /checkall, inline /check handlers

# ─── SIMPLE PERSISTENT MEMORY (per chat) ──────────────────────────
_memory: Dict[str, List[dict]] = {}   # key: str(chat_id)
_emoji_pref: Dict[int, bool] = {}     # True=allow sparse emojis, False=strip all

NO_EMOJI_PATTERNS = [
    r"\bno\s*emoji(?:s)?\b",
    r"\bstop\s*using\s*emoji(?:s)?\b",
    r"\bwithout\s*emoji(?:s)?\b",
    r"\bemoji\s*free\b",
    r"\bno\s*emojis\b",
]

YES_EMOJI_PATTERNS = [
    r"\buse\s*emoji(?:s)?\b",
    r"\bwith\s*emoji(?:s)?\b",
]

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
    if len(_memory[key]) > MAX_MEMORY:
        _memory[key] = _memory[key][-MAX_MEMORY:]
    _save_memory()

def _update_emoji_pref(chat_id: int, user_text: str):
    text = (user_text or "").lower()
    for p in NO_EMOJI_PATTERNS:
        if re.search(p, text):
            _emoji_pref[chat_id] = False
            return
    for p in YES_EMOJI_PATTERNS:
        if re.search(p, text):
            _emoji_pref[chat_id] = True
            return
    # if no explicit instruction, leave existing preference as-is (default True)

def _build_context(chat_id: int, user_text: str) -> str:
    """Build a single prompt string with short context so SafoneAPI can 'remember'."""
    msgs = _memory.get(str(chat_id), [])[-(MAX_MEMORY - 1):]
    ctx_lines: List[str] = []
    for m in msgs:
        r = m.get("role", "user")
        c = (m.get("content", "") or "").replace("\n", " ").strip()
        if c:
            ctx_lines.append(f"{r.title()}: {c}")
    ctx = "\n".join(ctx_lines)

    guidelines = (
        "Guidelines: Be concise and helpful. Use emojis sparingly only if they add clarity. "
        "If the user asked to avoid emojis, do not use any. "
        "Avoid markdown headings like '##'; use simple lines."
    )

    prefix = f"Previous conversation:\n{ctx}\n\n" if ctx else ""
    prompt = f"{prefix}User: {user_text}\n\n{guidelines}"
    return prompt

# ─── Emoji utilities (limit or strip) ─────────────────────────────
def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x1F300 <= cp <= 0x1F5FF or   # symbols & pictographs
        0x1F600 <= cp <= 0x1F64F or   # emoticons
        0x1F680 <= cp <= 0x1F6FF or   # transport & map
        0x1F700 <= cp <= 0x1F77F or
        0x1F780 <= cp <= 0x1F7FF or
        0x1F800 <= cp <= 0x1F8FF or
        0x1F900 <= cp <= 0x1F9FF or   # supplemental symbols & pictographs
        0x1FA00 <= cp <= 0x1FAFF or
        0x2600  <= cp <= 0x26FF  or   # misc symbols
        0x2700  <= cp <= 0x27BF  or   # dingbats
        0xFE00  <= cp <= 0xFE0F  or   # variation selectors
        0x1F1E6 <= cp <= 0x1F1FF or   # flags
        cp == 0x20E3                  # keycap
    )

def _format_response(text: str, allow_emojis: bool) -> str:
    text = text or ""
    # Normalize headings & bullets (no emoji bullets)
    lines = text.splitlines()
    out_lines: List[str] = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("##"):
            s = "• " + s.lstrip("#").strip()
        elif s.startswith("* ") or s.startswith("- "):
            s = "• " + s[2:].strip()
        out_lines.append(s)
    normalized = "\n".join(out_lines).strip()

    if not allow_emojis:
        # strip all emojis
        return "".join(ch for ch in normalized if not _is_emoji(ch)).strip()

    # allow at most 2 emojis total
    count = 0
    kept_chars: List[str] = []
    for ch in normalized:
        if _is_emoji(ch):
            count += 1
            if count <= 2:
                kept_chars.append(ch)
            # else: skip extra emojis
        else:
            kept_chars.append(ch)
    return "".join(kept_chars).strip()

# ─── /act & /actnot Commands (DMs) ────────────────────────────────
@dp.message(Command("act"))
async def activate_chatgpt(message: Message):
    if message.chat.type != "private":
        return await message.reply("🤖 /act only works in a private chat.")
    chatgpt_enabled[message.from_user.id] = True
    await message.reply("ChatGPT fallback is now ON for your DMs.")

@dp.message(Command("actnot"))
async def deactivate_chatgpt(message: Message):
    if message.chat.type != "private":
        return await message.reply("🤖 /actnot only works in a private chat.")
    chatgpt_enabled[message.from_user.id] = False
    await message.reply("ChatGPT fallback is now OFF for your DMs.")

# ─── ChatGPT Fallback (DMs) with memory + emoji rules ─────────────
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
        _update_emoji_pref(message.chat.id, text)
        _append_memory(message.chat.id, "user", text)
        prompt = _build_context(message.chat.id, text)
        resp   = await api.chatgpt(prompt)
        answer = getattr(resp, "message", None) or str(resp)
        allow  = _emoji_pref.get(message.chat.id, True)
        answer = _format_response(answer, allow)
        _append_memory(message.chat.id, "assistant", answer)
        await message.answer(html.escape(answer))
    except Exception:
        logger.exception("chatgpt error")
        await message.reply("SafoneAPI failed or no response.")

# ─── Group/Supergroup handler ─────────────────────────────────────
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
    txt = (message.text or "").strip()
    if txt and len(txt) <= 200:
        _append_memory(message.chat.id, "user", f"[group context] {txt}")

    if not _is_addressed_to_bot(message):
        return

    text = _strip_bot_mention(txt)
    if not text:
        return

    try:
        _update_emoji_pref(message.chat.id, text)
        _append_memory(message.chat.id, "user", text)
        prompt = _build_context(message.chat.id, text)
        resp   = await api.chatgpt(prompt)
        answer = getattr(resp, "message", None) or str(resp)
        allow  = _emoji_pref.get(message.chat.id, True)
        answer = _format_response(answer, allow)
        _append_memory(message.chat.id, "assistant", answer)
        await message.reply(html.escape(answer))
    except Exception as e:
        logger.exception(f"group chatgpt error: {e}")
        await message.reply("Couldn't get a reply right now.")

# ─── INLINE: Restricted-only scan (no collision with other inline) ────────────
# Triggers: query starts with "chk", "res", or "restricted" (case-insensitive)
# Usage: @YourBotName chk
import aiohttp

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_RESTRICT_PATTERNS = [
    re.compile(r"\brestricted on Telegram\b", re.I),
    re.compile(r"\bThis phone number is restricted\b", re.I),
    re.compile(r"\bBlocked\b", re.I),
]

def _canonical_num(tok: str) -> str:
    return re.sub(r"\D", "", (tok or ""))

def _is_restricted_html(html_text: str) -> Optional[bool]:
    if not html_text:
        return None
    for p in _RESTRICT_PATTERNS:
        if p.search(html_text):
            return True
    return False  # reachable page without matches → not restricted

async def _fetch_status_inline(
    session: aiohttp.ClientSession,
    num: str,
    sem: asyncio.Semaphore,
    timeout_total: float,
) -> Tuple[str, Optional[bool]]:
    url = f"https://fragment.com/phone/{num}"
    try:
        async with sem:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout_total)) as resp:
                txt = await resp.text(errors="ignore")
                return num, _is_restricted_html(txt)
    except Exception as e:
        logger.warning(f"[inline] fetch failed for {num}: {e!r}")
        return num, None

INLINE_TRIGGERS = {"chk", "res", "restricted"}

@dp.inline_query(F.query.func(lambda q: bool(q) and (q.strip().split()[0].lower() in INLINE_TRIGGERS)))
async def inline_restricted_scan(inline_q: InlineQuery):
    """
    Scans saved numbers (fragment._saves) and returns ONLY restricted ones.
    Filtered by first token in query, so other inline handlers (e.g., fragment_url) won't collide.
    """
    uid = inline_q.from_user.id
    nums = fragment._saves.get(uid, []) if hasattr(fragment, "_saves") else []

    if not nums:
        article = InlineQueryResultArticle(
            id="no_saved",
            title="📭 No saved numbers",
            input_message_content=InputTextMessageContent(
                "📭 No numbers saved. Use <code>/save</code> first.", parse_mode="HTML"
            ),
            description="Use /save to add numbers",
        )
        return await inline_q.answer([article], cache_time=0, is_personal=True)

    # normalize, dedupe, sort
    norm = sorted(set(_canonical_num(n) for n in nums if _canonical_num(n)))

    # Inline should be fast
    concurrency = min(len(norm), 50)
    sem = asyncio.Semaphore(concurrency)
    timeout_total = 5.0
    conn = aiohttp.TCPConnector(limit_per_host=concurrency, ssl=False)

    async with aiohttp.ClientSession(connector=conn, headers=_DEFAULT_HEADERS) as sess:
        results = await asyncio.gather(
            *(_fetch_status_inline(sess, n, sem, timeout_total) for n in norm),
            return_exceptions=False,
        )

    restricted = [n for n, ok in results if ok is True]
    unknown    = [n for n, ok in results if ok is None]

    if restricted:
        # keep body under inline message limits
        body = "\n".join(
            f"🔒 <a href='https://fragment.com/phone/{n}'>{n}</a>"
            for n in restricted[:400]
        )
    else:
        body = "✅ No restricted numbers found."

    if unknown:
        body += "\n\n⚠️ Could not verify (sample):\n" + "\n".join(unknown[:20])
        if len(unknown) > 20:
            body += f"\n…(+{len(unknown) - 20} more)"

    title = f"🔍 Restricted: {len(restricted)} | ⚠️ Unknown: {len(unknown)}"

    article = InlineQueryResultArticle(
        id="restricted_only",
        title=title,
        input_message_content=InputTextMessageContent(body, parse_mode="HTML"),
        description="Show only restricted numbers (and unknown if any)",
    )
    # cache_time=0 + is_personal → fresh, per-user
    await inline_q.answer([article], cache_time=0, is_personal=True)

# ─── STARTUP ───────────────────────────────────────────────────────
@dp.startup()
async def on_startup():
    global BOT_USERNAME, BOT_ID
    _load_memory()
    me = await bot.get_me()
    BOT_USERNAME = (me.username or "").strip()
    BOT_ID = me.id
    logger.info(f"@{BOT_USERNAME} (id={BOT_ID}) is up. Memory file: {MEMORY_FILE}")

# ─── RUN ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("Bot is starting…")
    dp.run_polling(bot, skip_updates=True, reset_webhook=True)
