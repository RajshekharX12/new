#!/usr/bin/env python3
"""
update.py

Handler for /update:
  1) Pull latest code
  2) Install any new Python dependencies
  3) Show added/modified/removed files
  4) Ask ChatGPT for a clear breakdown:
     • Features Added
     • Features Modified
     • Features Removed
"""

import sys
import os
import subprocess
import logging
import asyncio

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

        # 2) Pull from remote
        subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT)

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

        # 4) Record new commit
        new_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.STDOUT
        ).decode().strip()

        # 5) Diff name-status between commits
        diff = subprocess.check_output(
            ["git", "diff", "--name-status", old_sha, new_sha],
            stderr=subprocess.STDOUT
        ).decode().splitlines()

        added    = [ln.split("\t",1)[1] for ln in diff if ln.startswith("A\t")]
        modified = [ln.split("\t",1)[1] for ln in diff if ln.startswith("M\t")]
        removed  = [ln.split("\t",1)[1] for ln in diff if ln.startswith("D\t")]

        # 6) Remove the initial status
        await status.delete()

        # 7) Show raw file summary
        added_list    = added    or ["None"]
        modified_list = modified or ["None"]
        removed_list  = removed  or ["None"]

        raw_lines = [
            "✅ *Update Complete!*",
            "",
            "✨ *Added:*",
            *(f"• {f}" for f in added_list),
            "",
            "🛠 *Modified:*",
            *(f"• {f}" for f in modified_list),
            "",
            "❌ *Removed:*",
            *(f"• {f}" for f in removed_list),
        ]
        await message.answer("\n".join(raw_lines), parse_mode="Markdown")

        # 8) Detailed breakdown prompt for ChatGPT
        a_str = "\n".join(f"- {f}" for f in added)    if added    else "- None"
        m_str = "\n".join(f"- {f}" for f in modified) if modified else "- None"
        r_str = "\n".join(f"- {f}" for f in removed)  if removed  else "- None"

        prompt = (
            "The repository was updated with these file changes:\n"
            f"Added files:\n{a_str}\n\n"
            f"Modified files:\n{m_str}\n\n"
            f"Removed files:\n{r_str}\n\n"
            "Please give me a clear breakdown under three headings:\n"
            "• *Features Added:* describe new functionality.\n"
            "• *Features Modified:* describe updates to existing functionality.\n"
            "• *Features Removed:* describe removed functionality.\n"
            "Use brief bullet points and emojis under each heading."
        )
        resp     = await api.chatgpt(prompt)
        detailed = getattr(resp, "message", str(resp)).strip()

        await message.answer(f"*Detailed Change Explanation:*\n{detailed}", parse_mode="Markdown")

        # 9) Final confirmation
        await message.answer("✅ Bot is up-to-date and dependencies installed!")

    except Exception as e:
        logger.exception("Error in update")
        err = getattr(e, "output", str(e))
        await status.edit_text(f"❌ Update failed:\n{err}", parse_mode="Markdown")
