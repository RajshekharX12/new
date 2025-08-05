# speed.py

import sys
import os
import json
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
        raw = await asyncio.wait_for(
            run_in_executor(
                subprocess.check_output,
                ["speedtest-cli", "--json"],
                {"stderr": subprocess.STDOUT, "text": True}
            ),
            timeout=90
        )
        data = json.loads(raw)
        download = data["download"] / 1_000_000
        upload = data["upload"] / 1_000_000
        ping = data["ping"]

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
            "⚠️ `speedtest-cli` not found. Install with:\n"
            "`pip install speedtest-cli`"
        )
    except subprocess.CalledProcessError as e:
        logger.exception("speedtest-cli failed")
        await status.edit_text(f"⚠️ speedtest-cli error:\n<code>{e.output}</code>")
    except Exception as e:
        logger.exception("Unexpected speedtest error")
        await status.edit_text(f"⚠️ Speed test failed: {e}")


@dp.message(Command("exec"))
async def exec_handler(message: Message):
    """Run a shell command on the VPS and return its output or a ChatGPT summary."""
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
        out = e.output

    # if output is large, summarize via ChatGPT
    if len(out) > 1000:
        summary_prompt = (
            f"Here is the output of the command `{cmd}`:\n```\n{out}\n```\n"
            "Please provide a concise breakdown of key points or errors in bullet points."
        )
        try:
            resp = await api.chatgpt(summary_prompt)
            summary = getattr(resp, "message", str(resp))
            await status.edit_text(f"📄 Summary:\n{summary}")
        except Exception as e:
            logger.exception("exec summarization error")
            await status.edit_text(
                f"⚠️ Output too long and summarization failed: {e}"
            )
    else:
        # send full output
        safe = html.escape(out)
        await status.edit_text(f"```\n{safe}\n```", parse_mode="Markdown")
