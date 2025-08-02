#!/usr/bin/env python3
"""
update.py

Handler for /update:
  1) Pull latest code (and show pull output)
  2) Install any new Python dependencies
  3) Show added/modified/removed files
  4) Ask ChatGPT for a detailed breakdown
"""

import sys, os, subprocess, logging, asyncio
from aiogram.filters import Command
from aiogram.types import Message
from SafoneAPI import SafoneAPI

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp
bot   = _main.bot

logger = logging.getLogger(__name__)
api = SafoneAPI()

@dp.message(Command(commands=["update"]))
async def update_handler(message: Message):
    status = await message.reply("🔄 Pulling latest code…")
    try:
        # 1) Record current commit
        old_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.STDOUT
        ).decode().strip()

        # 2) Pull from remote, capture and show output
        pull_out = subprocess.check_output(
            ["git", "pull"], stderr=subprocess.STDOUT
        ).decode().strip()
        await message.reply(f"📥 Git Pull Output:\n```\n{pull_out}\n```", parse_mode="Markdown")

        # 3) Install any new dependencies
        await message.reply("📦 Installing dependencies…")
        loop = asyncio.get_event_loop()
        try:
            install_out = await loop.run_in_executor(
                None,
                subprocess.check_output,
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                subprocess.STDOUT
            )
            install_out = install_out.decode().strip()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"❌ Pip install failed:\n{e.output.decode()}")

        # 4) Record new commit and diff changes…
        new_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.STDOUT
        ).decode().strip()
        diff = subprocess.check_output(
            ["git", "diff", "--name-status", old_sha, new_sha],
            stderr=subprocess.STDOUT
        ).decode().splitlines()

        added    = [ln.split("\t",1)[1] for ln in diff if ln.startswith("A\t")]
        modified = [ln.split("\t",1)[1] for ln in diff if ln.startswith("M\t")]
        removed  = [ln.split("\t",1)[1] for ln in diff if ln.startswith("D\t")]

        await status.delete()

        # … (rest of your logic for summarizing files and ChatGPT breakdown) …

    except Exception as e:
        logger.exception("Error in update")
        err = getattr(e, "output", str(e))
        await status.edit_text(f"❌ Update failed:\n{err}", parse_mode="Markdown")
