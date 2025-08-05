import sys
import subprocess
import logging
import os
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

        # 2) Build prompt with file list and emoji headings
        prompt = (
            "🛑 Top 5 Problems\n"
            + "\n".join(f"- {f}: describe issue" for f in files)  # placeholder
            + "\n\n✅ Fixes\n"
            + "\n".join(f"- {f}: describe fix" for f in files)
            + "\n\nDo not include any other text. Start with '🛑 Top 5 Problems'."
        )

        # 3) Ask ChatGPT for problems and fixes
        resp = await api.chatgpt(prompt)
        review_text = getattr(resp, "message", str(resp)).strip()

        # 4) Replace the loading message with the review
        await status.delete()
        await message.answer(f"📋 Code Review\n\n{review_text}", parse_mode="Markdown")

    except Exception as e:
        logger.exception("review error")
        await status.edit_text(f"❌ Code review failed: {e}")

@dp.message(Command("exec"))
async def exec_handler(message: Message):
    status = await message.reply("⏳ Running command...")
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await status.edit_text("⚠️ Usage: `/exec <shell command>`", parse_mode="Markdown")

    cmd = parts[1]
    try:
        out = subprocess.check_output(
            cmd, shell=True, cwd=os.getcwd(), stderr=subprocess.STDOUT, text=True
        )
    except subprocess.CalledProcessError as e:
        out = e.output

    # If output is large, summarize via ChatGPT
    if len(out) > 1000:
        prompt = (
            f"Here is the output of the shell command `{cmd}`:\n```
{out}
```\n"
            "Please provide a concise breakdown of the key points and any errors in bullet points."
        )
        try:
            resp = await api.chatgpt(prompt)
            summary = getattr(resp, "message", str(resp))
            await status.edit_text(f"📄 Summary:\n{summary}")
        except Exception as e:
            logger.exception("exec summarization error")
            await status.edit_text(f"⚠️ Command output too long, summarization failed: {e}")
    else:
        # Send full output
        text = f"```
{out}
```"
        await status.edit_text(text, parse_mode="Markdown")
