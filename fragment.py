#!/usr/bin/env python3
# bot.py — merged main.py + fragment.py (aiogram 3.14 compatible)
import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import aiohttp
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message

# ============================== CONFIG ==============================

def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

BOT_TOKEN = _env("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required in environment")

# Optional Fragment cookies/tokens for richer responses
FRAGMENT_HASH        = _env("FRAGMENT_HASH")
FRAGMENT_STEL_SSID   = _env("FRAGMENT_STEL_SSID")
FRAGMENT_STEL_TON    = _env("FRAGMENT_STEL_TON_TOKEN")
FRAGMENT_STEL_TOKEN  = _env("FRAGMENT_STEL_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("bot")

# ========================== FRAGMENT CLIENT =========================

@dataclass
class FragmentCredentials:
    hash: str = ""
    stel_ssid: str = ""
    stel_ton_token: str = ""
    stel_token: str = ""

class FragmentAPI:
    def __init__(self, creds: FragmentCredentials):
        self.creds = creds

    def _cookie_jar(self) -> aiohttp.CookieJar:
        jar = aiohttp.CookieJar()
        if self.creds.stel_ssid:
            jar.update_cookies({"stel_ssid": self.creds.stel_ssid})
        if self.creds.stel_ton_token:
            jar.update_cookies({"stel_ton_token": self.creds.stel_ton_token})
        if self.creds.stel_token:
            jar.update_cookies({"stel_token": self.creds.stel_token})
        if self.creds.hash:
            jar.update_cookies({"hash": self.creds.hash})
        return jar

    async def is_number_connected(self, session: aiohttp.ClientSession, num: str) -> Optional[bool]:
        """
        Returns:
            True  -> connected to a Telegram account
            False -> free (not connected)
            None  -> unknown (couldn't determine)
        Strategy: Fetch the number page and look for keywords / JSON state.
        """
        url = f"https://fragment.com/number/{num}"
        try:
            async with session.get(url, timeout=15) as resp:
                txt = await resp.text()
        except Exception as e:
            logger.warning("Fetch failed for %s: %s", num, e)
            return None

        lower = txt.lower()
        # Phrase heuristics
        if "connected to a telegram account" in lower or "already linked" in lower or "busy" in lower:
            return True
        if "free" in lower or "available" in lower or "not connected" in lower:
            return False

        # Try to parse Next.js dehydrated state quickly (without JSON parsing deps)
        m = re.search(r'__NEXT_DATA__"\s*type="application/json">\s*({.*?})\s*<', txt, re.S)
        if m:
            blob = m.group(1)
            if '"busy":true' in blob or '"status":"busy"' in blob:
                return True
            if '"busy":false' in blob or '"status":"free"' in blob:
                return False

        return None

_fragment_api: Optional[FragmentAPI] = None

def init_fragment_api() -> None:
    global _fragment_api
    creds = FragmentCredentials(
        hash=FRAGMENT_HASH,
        stel_ssid=FRAGMENT_STEL_SSID,
        stel_ton_token=FRAGMENT_STEL_TON,
        stel_token=FRAGMENT_STEL_TOKEN
    )
    _fragment_api = FragmentAPI(creds)
    has_cookies = any([FRAGMENT_HASH, FRAGMENT_STEL_SSID, FRAGMENT_STEL_TON, FRAGMENT_STEL_TOKEN])
    logger.info("Fragment API initialized (cookies=%s)", "yes" if has_cookies else "no")

# ============================ HELPERS ==============================

_digits = re.compile(r'\D+')

def _canonical(num: str) -> str:
    """Keep digits only and ensure 888 prefix."""
    s = _digits.sub("", num or "")
    if not s:
        return s
    if not s.startswith("888"):
        s = "888" + s
    return s

def _fmt_list_with_status(nums: List[str], statuses: Dict[str, Optional[bool]], total: Optional[int]) -> str:
    lines: List[str] = []
    count = len(nums)
    header_total = total if (total and total >= count) else count
    lines.append(f"🔒 Restricted: {count}/{header_total}")
    for idx, n in enumerate(nums, 1):
        st = statuses.get(n)
        if st is True:
            tag = "❌ connected to an account"
        elif st is False:
            tag = "✅ Free"
        else:
            tag = "⚠️ Unknown"
        lines.append(f"{idx}. 🔒 {n} — {tag}")
    return "\n".join(lines)

async def _bulk_check_connected(nums: List[str]) -> Dict[str, Optional[bool]]:
    """
    Query Fragment for each number concurrently.
    Returns a mapping num -> True/False/None.
    """
    out: Dict[str, Optional[bool]] = {}
    if not nums:
        return out

    if _fragment_api is None:
        init_fragment_api()

    jar = _fragment_api._cookie_jar() if _fragment_api else aiohttp.CookieJar()
    connector = aiohttp.TCPConnector(limit=20)  # concurrency cap
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(
        cookie_jar=jar,
        timeout=timeout,
        connector=connector,
        headers={"User-Agent": "Mozilla/5.0 (compatible; NFTCheckerBot/1.0)"}
    ) as session:
        sem = asyncio.Semaphore(10)

        async def one(n: str):
            c = _canonical(n)
            if not c:
                out[n] = None
                return
            try:
                async with sem:
                    res = await _fragment_api.is_number_connected(session, c)  # type: ignore[union-attr]
                out[c] = res
            except Exception as e:
                logger.warning("check failed for %s: %s", c, e)
                out[c] = None

        await asyncio.gather(*(one(n) for n in nums))

    return out

# ============================ STATE ================================

router = Router()
_saved_numbers: Dict[int, List[str]] = {}
_last_restricted_total: Dict[int, int] = {}

# ============================ COMMANDS =============================

@router.message(Command("save"))
async def cmd_save(message: Message):
    """
    /save 88801234567 12345 88800001111
    Saves numbers for the user (canonicalizes to 888 prefix).
    """
    parts = (message.text or "").split()
    given = parts[1:]
    if not given:
        return await message.reply("Usage: <code>/save 88801234567 12345 ...</code>")

    uid = message.from_user.id
    have = _saved_numbers.setdefault(uid, [])
    added = 0
    for p in given:
        c = _canonical(p)
        if c and c not in have:
            have.append(c)
            added += 1
    have.sort()
    await message.reply(f"Saved {added} number(s). Total now: <b>{len(have)}</b>.")

@router.message(Command("list"))
async def cmd_list(message: Message):
    uid = message.from_user.id
    nums = _saved_numbers.get(uid, [])
    if not nums:
        return await message.reply("No numbers saved yet.")
    body = "\n".join(f"{i+1}. {n}" for i, n in enumerate(nums))
    await message.reply(f"<b>Saved numbers ({len(nums)}):</b>\n{body}")

@router.message(Command("clear"))
async def cmd_clear(message: Message):
    uid = message.from_user.id
    _saved_numbers.pop(uid, None)
    _last_restricted_total.pop(uid, None)
    await message.reply("Cleared your saved numbers.")

@router.message(Command("checkall"))
async def cmd_checkall(message: Message):
    """
    Checks saved numbers, takes first 5 (or all if ≤5), and prints the 'Restricted' list annotated.
    """
    uid = message.from_user.id
    nums = _saved_numbers.get(uid, [])
    if not nums:
        return await message.reply("No numbers to check. Use /save first.")

    sample = nums[:5] if len(nums) > 5 else nums
    _last_restricted_total[uid] = len(nums)

    status_msg = await message.reply(f"Checking {len(sample)} numbers…")
    statuses = await _bulk_check_connected(sample)
    total = _last_restricted_total.get(uid, len(sample))
    text = _fmt_list_with_status(sample, statuses, total)
    await status_msg.edit_text(text)

@router.message(Command("restricted"))
async def cmd_restricted(message: Message):
    """
    Paste your restricted numbers to annotate:
    /restricted 88801457239 88802473528 88802692410 88803649531 88804365729
    """
    parts = (message.text or "").split()
    given = [_canonical(p) for p in parts[1:] if p.strip()]
    given = [g for g in given if g]
    if not given:
        return await message.reply("Usage: <code>/restricted <num1> <num2> ...</code>")

    _last_restricted_total[message.from_user.id] = len(given)
    status_msg = await message.reply(f"Annotating {len(given)} restricted numbers…")
    statuses = await _bulk_check_connected(given)
    text = _fmt_list_with_status(given, statuses, len(given))
    await status_msg.edit_text(text)

# ============================ BOOTSTRAP ============================

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp.include_router(router)

if __name__ == "__main__":
    init_fragment_api()
    logger.info("Starting bot polling…")
    dp.run_polling(bot, skip_updates=True, reset_webhook=True)
