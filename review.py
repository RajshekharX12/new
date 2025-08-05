import sys
import subprocess
import logging
from aiogram.filters import Command
from aiogram.types import Message
from SafoneAPI import SafoneAPI

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp = _main.dp

logger = logging.getLogger(__name__)
api = SafoneAPI()

@dp.message(Command("review"))
async def review_handler(message: Message):
    status = await message.reply("🔍 Running code review…")
    try:
        # 1) Get all Python files
        files = subprocess.check_output(
            ["git", "ls-files", "*.py"], stderr=subprocess.STDOUT
        ).decode().splitlines()
        if not files:
            raise ValueError("No Python files found in repo.")

        # 2) Build prompt for top 5 issues and fixes with emoji headings
        prompt = (
            "You are a concise code reviewer. The repository contains these Python files:\n"
            + "".join(f"• {f}\n" for f in files)
            + "\n"
            "🛑 Top 5 Problems\n"
            "- For each of the five most critical issues, write one bullet as 'filename.py: issue description'\n\n"
            "✅ Fixes\n"
            "- Provide a one-line fix suggestion for each problem above, in the same order.\n\n"
            "Do not include any other text or mention GPT or AI. Start directly with '🛑 Top 5 Problems'."
        )

        # 3) Send prompt to ChatGPT via SafoneAPI
        resp = await api.chatgpt(prompt)
        review_text = getattr(resp, "message", str(resp)).strip()

        # 4) Replace the status with final review
        await status.delete()
        await message.answer(
            f"📋 Code Review\n\n{review_text}",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.exception("review error")
        await status.edit_text(f"❌ Code review failed: {e}")
