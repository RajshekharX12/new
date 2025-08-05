import sys
import asyncio
import logging
import speedtest

from aiogram.filters import Command
from aiogram.types import Message

# grab dispatcher from main
_main = sys.modules["__main__"]
dp = _main.dp

logger = logging.getLogger(__name__)

# simple in-memory cache to avoid repeat tests
_cache = {"ts": 0, "text": None}
CACHE_TTL = 300  # seconds

async def run_in_executor(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)

@dp.message(Command("speed"))
async def send_speed(message: Message):
    now = asyncio.get_event_loop().time()
    if _cache["text"] and now - _cache["ts"] < CACHE_TTL:
        return await message.reply("♻️ Using cached results:\n" + _cache["text"])

    status = await message.reply("⏳ Finding best server…")
    try:
        st = await asyncio.wait_for(run_in_executor(speedtest.Speedtest), timeout=30)
        await status.edit_text("🔍 Finding best server…")
        await asyncio.wait_for(run_in_executor(st.get_best_server), timeout=30)

        await status.edit_text("⬇️ Testing download speed…")
        dl = await asyncio.wait_for(run_in_executor(st.download), timeout=60)

        await status.edit_text("⬆️ Testing upload speed…")
        ul = await asyncio.wait_for(run_in_executor(lambda: st.upload(pre_allocate=False)), timeout=60)

        ping = st.results.ping
        text = (
            f"📶 **VPS Speed Test**\n"
            f"• Download: **{dl/1_000_000:.2f} Mbps**\n"
            f"• Upload:   **{ul/1_000_000:.2f} Mbps**\n"
            f"• Ping:     **{ping:.2f} ms**"
        )
        _cache.update({"ts": now, "text": text})
        await status.edit_text(text, parse_mode="Markdown")

    except asyncio.TimeoutError:
        await status.edit_text("❌ Speed test timed out. Please try again later.")
    except Exception as e:
        logger.exception("Speed test error")
        await status.edit_text(f"⚠️ Speed test failed: {e}")
