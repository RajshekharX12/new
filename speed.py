import sys
import os
import json
import html
import logging
import subprocess
import asyncio

from aiogram.filters import Command
from aiogram.types import Message

# grab dispatcher & bot from main
_main = sys.modules.get("__main__")
dp = getattr(_main, 'dp', None)

logger = logging.getLogger(__name__)

async def run_in_executor(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

@dp.message(Command("speed"))
async def send_speed(message: Message):
    status = await message.reply("⏳ Running speedtest-cli…")
    try:
        # Run speedtest-cli with --json
        raw = await asyncio.wait_for(
            run_in_executor(
                subprocess.check_output,
                ["speedtest-cli", "--json"],
                stderr=subprocess.STDOUT,
                text=True
            ),
            timeout=90
        )
        data = json.loads(raw)
        download = data.get("download", 0) / 1_000_000
        upload = data.get("upload", 0) / 1_000_000
        ping = data.get("ping", 0)

        text = (
            "📶 <b>VPS Speed Test</b>\n"
            f"• Download: <b>{download:.2f} Mbps</b>\n"
            f"• Upload:   <b>{upload:.2f} Mbps</b>\n"
            f"• Ping:     <b>{ping:.2f} ms</b>"
        )
        await status.edit_text(text, parse_mode="HTML")

    except asyncio.TimeoutError:
        await status.edit_text("❌ Speed test timed out. Please try again later.")
    except FileNotFoundError:
        await status.edit_text(
            "⚠️ <code>speedtest-cli</code> not found. Install with:\n<code>pip install speedtest-cli</code>",
            parse_mode="HTML"
        )
    except subprocess.CalledProcessError as e:
        logger.exception("speedtest-cli failed")
        safe = html.escape(e.output or str(e))
        await status.edit_text(
            f"<b>⚠️ speedtest-cli error:</b>\n<pre>{safe}</pre>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.exception("Unexpected speedtest error")
        await status.edit_text(f"⚠️ Speed test failed: {e}")

@dp.message(Command("exec"))
async def exec_handler(message: Message):
    """Run a shell command on the VPS and return raw output."""
    status = await message.reply("⏳ Running command…")
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await status.edit_text(
            "⚠️ Usage: <code>/exec &lt;shell command&gt;</code>", parse_mode="HTML"
        )
    cmd = parts[1]

    try:
        out = subprocess.check_output(
            cmd,
            shell=True,
            cwd=os.getcwd(),
            stderr=subprocess.STDOUT,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        out = e.output or str(e)
    except Exception as e:
        out = f"(failed to run command: {e})"

    if not out.strip():
        out = "(no output)"

    # Telegram message length safety
    safe_out = html.escape(out)
    MAX = 3500  # leave headroom for markup
    if len(safe_out) > MAX:
        safe_out = safe_out[:MAX] + "\n…(truncated)"

    await status.edit_text(f"📄 <b>Output:</b>\n<pre>{safe_out}</pre>", parse_mode="HTML")
