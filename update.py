import sys
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
        # 1) Record old HEAD
        old_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.STDOUT
        ).decode().strip()

        # 2) Git pull
        subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT)

        # 3) Record new HEAD
        new_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.STDOUT
        ).decode().strip()

        # 4) Get diff of names and statuses
        diff_output = subprocess.check_output(
            ["git", "diff", "--name-status", old_sha, new_sha],
            stderr=subprocess.STDOUT
        ).decode().splitlines()

        added = [line.split("\t",1)[1] for line in diff_output if line.startswith("A\t")]
        removed = [line.split("\t",1)[1] for line in diff_output if line.startswith("D\t")]

        # 5) Remove status message
        await status.delete()

        # 6) Raw file summary
        added_section = [f"• {p}" for p in added] or ["• None"]
        removed_section = [f"• {p}" for p in removed] or ["• None"]

        raw_lines = [
            "✅ *Update complete!*",
            "",
            "✨ *Added:*",
            *added_section,
            "",
            "❌ *Removed:*",
            *removed_section,
        ]
        await message.answer("\n".join(raw_lines), parse_mode="Markdown")

        # 7) Ask ChatGPT for concise summary
        added_str = "\n".join(f"- {p}" for p in added) if added else "- None"
        removed_str = "\n".join(f"- {p}" for p in removed) if removed else "- None"

        prompt = (
            "Repo update:\n"
            f"Added files:\n{added_str}\n"
            f"Removed files:\n{removed_str}\n\n"
            "In one short bullet, describe what was *added*.\n"
            "In one short bullet, describe what was *removed*."
        )
        resp = await api.chatgpt(prompt)
        summary = getattr(resp, "message", str(resp)).strip()

        # 8) Send the one-line summary
        await message.answer(f"*Change Summary:*\n{summary}", parse_mode="Markdown")

    except subprocess.CalledProcessError as e:
        logger.exception("Git command failed")
        error_output = e.output.decode() if hasattr(e, "output") else str(e)
        await status.edit_text(
            f"❌ Update failed:\n```\n{error_output}\n```",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception("Unexpected error in update")
        await status.edit_text(f"❌ Update error: `{e}`", parse_mode="Markdown")
