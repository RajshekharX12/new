# update.py
#!/usr/bin/env python3
"""
update.py

Handler for /update:
  1) Pull latest code
  2) Show added/removed files
  3) Use ChatGPT for a one-bullet-per-category feature summary
  4) Restart the bot to apply updates
"""

import sys
import os
import subprocess
import logging
from aiogram.filters import Command
from aiogram.types import Message
from SafoneAPI import SafoneAPI

# Grab dispatcher & bot from main
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

        # 2) Pull
        subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT)

        # 3) New commit
        new_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.STDOUT
        ).decode().strip()

        # 4) Diff name-status
        diff_lines = subprocess.check_output(
            ["git", "diff", "--name-status", old_sha, new_sha],
            stderr=subprocess.STDOUT
        ).decode().splitlines()

        added   = [ln.split("\t",1)[1] for ln in diff_lines if ln.startswith("A\t")]
        removed = [ln.split("\t",1)[1] for ln in diff_lines if ln.startswith("D\t")]

        # 5) Delete the “pulling…” message
        await status.delete()

        # 6) Raw file summary
        added_list   = added or ["None"]
        removed_list = removed or ["None"]

        raw = [
            "✅ *Update complete!*",
            "",
            "✨ *Added:*",
            *(f"• {f}" for f in added_list),
            "",
            "❌ *Removed:*",
            *(f"• {f}" for f in removed_list),
        ]
        await message.answer("\n".join(raw), parse_mode="Markdown")

        # 7) ChatGPT feature summary prompt
        added_str   = "\n".join(f"- {f}" for f in added)   if added   else "- None"
        removed_str = "\n".join(f"- {f}" for f in removed) if removed else "- None"

        prompt = (
            "The repository was updated:\n"
            f"Added files:\n{added_str}\n"
            f"Removed files:\n{removed_str}\n\n"
            "In exactly two very short bullets, describe the *features* added and removed."
        )
        resp    = await api.chatgpt(prompt)
        summary = getattr(resp, "message", str(resp)).strip()

        # 8) Send the one-bullet summary
        await message.answer(f"*Feature Summary:*\n{summary}", parse_mode="Markdown")

        # 9) Restart process (hot-reload code)
        await message.answer("🔄 Restarting bot to apply updates…")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    except subprocess.CalledProcessError as e:
        logger.exception("Git command failed")
        out = e.output.decode() if hasattr(e, "output") else str(e)
        await status.edit_text(f"❌ Update failed:\n```\n{out}\n```", parse_mode="Markdown")
    except Exception as e:
        logger.exception("Unexpected error in update")
        await status.edit_text(f"❌ Update error: `{e}`", parse_mode="Markdown")
