import sys
import subprocess
import logging
from aiogram.filters import Command
from aiogram.types import Message
from SafoneAPI import SafoneAPI

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)
api = SafoneAPI()

@dp.message(Command("review"))
async def review_handler(message: Message):
    status = await message.reply("🔍 Running code review…")
    try:
        # 1) List all Python files in the repo
        files = subprocess.check_output(
            ["git", "ls-files", "*.py"], stderr=subprocess.STDOUT
        ).decode().splitlines()
        if not files:
            raise ValueError("No Python files found in repo.")

        # 2) Build a precise prompt with emoji headings
        prompt = (
            "You are a concise code reviewer. The repository contains these Python files:\n"
            + "".join(f"• {f}\n" for f in files)
            + "\n"
            "🛑 Top 5 Problems\n"
            "- List the five most critical issues, one per line (bullet points).\n\n"
            "✅ Fixes\n"
            "- For each problem above (in the same order), provide a one-line fix suggestion.\n\n"
            "Do not include any introductory text or mention GPT or AI. Start directly with '🛑 Top 5 Problems'."
        )

        # 3) Ask ChatGPT via SafoneAPI
        resp = await api.chatgpt(prompt)
        review_text = getattr(resp, "message", str(resp)).strip()

        # 4) Replace the loading message with the review
        await status.delete()
        await message.answer(f"📋 *Code Review*\n\n{review_text}", parse_mode="Markdown")

    except Exception as e:
        logger.exception("review error")
        await status.edit_text(f"❌ Code review failed: {e}")

