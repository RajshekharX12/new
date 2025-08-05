import sys
import os
import json
import html
import logging
import subprocess
import asyncio

from aiogram.filters import Command
from aiogram.types import Message
from SafoneAPI import SafoneAPI

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp = _main.dp

logger = logging.getLogger(__name__)
api = SafoneAPI()

async def run_in_executor(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)

@dp.message(Command("speed"))
async def send_speed(message: Message):
    status = await message.reply("⏳ Running speedtest-cli…")
    try:
        # Wrap check_output with kwargs in a zero-arg function
        def perform():
            return subprocess.check_output(
                ["speedtest-cli", "--json"],
                stderr=subprocess.STDOUT,
                text=True
            )
        raw = await asyncio.wait_for(run_in_executor(perform), timeout=90)
        data = json.loads(raw)
        download = data.get("download", 0) / 1_000_000
        upload   = data.get("upload", 0)   / 1_000_000
        ping     = data.get("ping", 0)
        text = (
            "📶 **VPS Speed Test**\n"
            f"• Download: **{download:.2f} Mbps**\n"
            f"• Upload:   **{upload:.2f} Mbps**\n"
            f"• Ping:     **{ping:.2f} ms**"
        )
        await status.edit_text(text, parse_mode="Markdown")

    except asyncio.TimeoutError:
        await status.edit_text("❌ Speed test timed out. Please try again later.")
    except FileNotFoundError:
        await status.edit_text(
            "⚠️ `speedtest-cli` not found. Install with:\n`pip install speedtest-cli`"
        )
    except subprocess.CalledProcessError as e:
        logger.exception("speedtest-cli failed")
        safe = html.escape(e.output or str(e))
        await status.edit_text(
            f"⚠️ speedtest-cli error:\n```
{safe}
```",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception("Unexpected speedtest error")
        await status.edit_text(f"⚠️ Speed test failed: {e}")

@dp.message(Command("exec"))
async def exec_handler(message: Message):
    """Run a shell command on the VPS and always return a short bullet summary."""
    status = await message.reply("⏳ Running command…")
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return await status.edit_text(
            "⚠️ Usage: `/exec <shell command>`", parse_mode="Markdown"
        )
    cmd = parts[1]

    try:
        out = subprocess.check_output(
            cmd, shell=True, cwd=os.getcwd(), stderr=subprocess.STDOUT, text=True
        )
    except subprocess.CalledProcessError as e:
        out = e.output or str(e)

    # Always use ChatGPT to produce a concise bullet-point summary
    try:
        prompt = (
            f"Here is the output of the command `{cmd}`:\n```
{out}
```\n"
            "Provide a concise bullet-point summary (one line each) "
            "highlighting each major step or completion message."
        )
        resp = await api.chatgpt(prompt)
        summary = getattr(resp, "message", str(resp)).strip()
        await status.edit_text(f"📄 Summary:\n{summary}")
    except Exception as e:
        logger.exception("exec summarization error")
        # If summarization fails, send a safe raw dump
        safe_out = html.escape(out)
        await status.edit_text(f"```
{safe_out}
```", parse_mode="Markdown")
