import sys
import json
import subprocess
import logging

from aiogram.filters import Command
from aiogram.types import Message

# grab dispatcher from main
_main = sys.modules["__main__"]
dp = _main.dp

logger = logging.getLogger(__name__)

@dp.message(Command("speed"))
async def send_speed(message: Message):
    # Make sure speedtest-cli is installed:
    # pip install speedtest-cli
    status = await message.reply("⏳ Running speedtest-cli…")
    try:
        # Call the CLI with JSON output
        raw = subprocess.check_output(
            ["speedtest-cli", "--json"],
            stderr=subprocess.STDOUT,
            text=True
        )
        data = json.loads(raw)

        download_mbps = data["download"] / 1_000_000
        upload_mbps   = data["upload"]   / 1_000_000
        ping_ms       = data["ping"]

        text = (
            "📶 **VPS Speed Test**\n"
            f"• Download: **{download_mbps:.2f} Mbps**\n"
            f"• Upload:   **{upload_mbps:.2f} Mbps**\n"
            f"• Ping:     **{ping_ms:.2f} ms**"
        )
        await status.edit_text(text, parse_mode="Markdown")

    except FileNotFoundError:
        # speedtest-cli not installed
        await status.edit_text(
            "⚠️ `speedtest-cli` not found. Please install it:\n"
            "`pip install speedtest-cli`"
        )
    except subprocess.CalledProcessError as e:
        logger.exception("speedtest-cli error")
        await status.edit_text(f"⚠️ speedtest-cli failed:\n<code>{e.output}</code>")
    except json.JSONDecodeError:
        await status.edit_text("⚠️ Failed to parse speedtest-cli output.")
    except Exception as e:
        logger.exception("Unexpected error")
        await status.edit_text(f"⚠️ Speed test failed: {e}")
