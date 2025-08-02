#!/usr/bin/env python3
"""
update.py

Handler for /update:
  1) Pull latest code
  2) Show added/modified/removed files
  3) Use ChatGPT for a three-bullet feature summary (Added / Modified / Removed)
  4) Hot-restart the bot so changes take effect immediately
"""

import sys
import os
import subprocess
import logging
from aiogram.filters import Command
from aiogram.types import Message
from SafoneAPI import SafoneAPI

# grab dp & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp
bot   = _main.bot

logger = logging.getLogger(__name__)
api = SafoneAPI()

@dp.message(Command(commands=["update"]))
async def update_handler(message: Message):
    status = await message.reply("🔄 Pulling latest code…")
    try:
        # record old & new SHAs
        old_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.STDOUT
        ).decode().strip()
        subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT)
        new_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.STDOUT
        ).decode().strip()

        # get name-status diff
        diff = subprocess.check_output(
            ["git", "diff", "--name-status", old_sha, new_sha],
            stderr=subprocess.STDOUT
        ).decode().splitlines()

        added   = [ln.split("\t",1)[1] for ln in diff if ln.startswith("A\t")]
        modified= [ln.split("\t",1)[1] for ln in diff if ln.startswith("M\t")]
        removed = [ln.split("\t",1)[1] for ln in diff if ln.startswith("D\t")]

        await status.delete()

        # raw summary
        a_list = added   or ["None"]
        m_list = modified or ["None"]
        r_list = removed or ["None"]

        raw = [
            "✅ *Update complete!*",
            "",
            "✨ *Added:*",
            *(f"• {f}" for f in a_list),
            "",
            "🛠 *Modified:*",
            *(f"• {f}" for f in m_list),
            "",
            "❌ *Removed:*",
            *(f"• {f}" for f in r_list),
        ]
        await message.answer("\n".join(raw), parse_mode="Markdown")

        # prepare ChatGPT prompt
        a_str = "\n".join(f"- {f}" for f in added)    if added    else "- None"
        m_str = "\n".join(f"- {f}" for f in modified) if modified else "- None"
        r_str = "\n".join(f"- {f}" for f in removed)  if removed  else "- None"

        prompt = (
            "The repo was updated:\n"
            f"Added files:\n{a_str}\n"
            f"Modified files:\n{m_str}\n"
            f"Removed files:\n{r_str}\n\n"
            "In exactly three very short bullets, describe:\n"
            "• one feature that was *added*\n"
            "• one feature that was *modified*\n"
            "• one feature that was *removed*"
        )
        resp    = await api.chatgpt(prompt)
        summary = getattr(resp, "message", str(resp)).strip()

        # send the concise feature summary
        await message.answer(f"*Feature Summary:*\n{summary}", parse_mode="Markdown")

        # hot-restart
        await message.answer("🔄 Restarting bot to apply updates…")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    except subprocess.CalledProcessError as e:
        logger.exception("Git command failed")
        out = e.output.decode() if hasattr(e, "output") else str(e)
        await status.edit_text(
            f"❌ Update failed:\n```\n{out}\n```", parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception("Unexpected error in update")
        await status.edit_text(f"❌ Update error: `{e}`", parse_mode="Markdown")
