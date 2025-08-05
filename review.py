import sys
import subprocess
import logging
from aiogram.filters import Command
from aiogram.types import Message
from SafoneAPI import SafoneAPI

# Grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)
api = SafoneAPI()

@dp.message(Command(commands=["review"]))
async def review_handler(message: Message):
    status = await message.reply("🔍 Running code review…")
    try:
        # 1) List all Python files in the repo
        files = subprocess.check_output(
            ["git", "ls-files", "*.py"], stderr=subprocess.STDOUT
        ).decode().splitlines()
        if not files:
            raise ValueError("No Python files found in repo.")

        # 2) Build a concise prompt
        prompt = (
            "You are a concise code reviewer. The repo contains these Python files:\n"
            + "".join(f"• {f}\n" for f in files)
            + "\n"
            "Please provide:\n"
            "## Quality Score (0–100%)\n"
            "## Problems (one line each — bullet points)\n"
            "## Suggestions (one line each — bullet points)\n"
            "Use Markdown headings exactly as above, and keep each line very short."
        )

        # 3) Ask ChatGPT via SafoneAPI
        resp = await api.chatgpt(prompt)
        review_text = getattr(resp, "message", str(resp)).strip()

        # 4) Replace the status message with the review
        await status.delete()
        await message.answer(
            f"📋 *Code Review*\n\n{review_text}",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.exception("review error")
        await status.edit_text(f"❌ Code review failed: {e}")

@dp.message(Command(commands=["help"]))
async def help_handler(message: Message):
    help_text = (
        "ℹ️ *Available Commands*\n\n"
        "• `/speed`  — run a VPS speed test 🌐\n"
        "• `/update` — pull latest code & report changes 🔄\n"
        "• `/review` — code quality review 📋\n"
        "• `/help`   — show this help message ❓\n\n"
        "✉️ Send any other text and I'll reply via ChatGPT ✨"
    )
    await message.answer(help_text, parse_mode="Markdown")
