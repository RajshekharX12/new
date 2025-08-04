import sys
import os
import subprocess
import logging
import asyncio
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from SafoneAPI import SafoneAPI

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp = _main.dp
bot = _main.bot

logger = logging.getLogger(__name__)
api = SafoneAPI()

# Configuration
SCREEN_SESSION = os.getenv("SCREEN_SESSION", "meow")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", 0))  # set your admin chat ID in .env
CHECK_INTERVAL = int(os.getenv("UPDATE_CHECK_INTERVAL", 3600))  # seconds between remote checks
PROJECT_PATH = os.getenv("PROJECT_PATH", os.getcwd())

last_remote_sha = None

async def run_update_process(chat_id: int):
    """
    Runs git pull, pip install, and computes diff.
    Returns tuple (pull_output, install_output, added, modified, removed).
    """
    # 1) Record current commit
    old_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()

    # 2) Pull from remote
    pull_out = subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT).decode().strip()

    # 3) Install dependencies
    try:
        install_out = subprocess.check_output([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ], stderr=subprocess.STDOUT).decode().strip()
    except subprocess.CalledProcessError as e:
        install_out = f"ERROR: {e.output.decode().strip()}"

    # 4) Get diff between SHAs
    new_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    diff_lines = subprocess.check_output([
        "git", "diff", "--name-status", old_sha, new_sha
    ], stderr=subprocess.STDOUT).decode().splitlines()

    added = [ln.split("\t",1)[1] for ln in diff_lines if ln.startswith("A\t")]
    modified = [ln.split("\t",1)[1] for ln in diff_lines if ln.startswith("M\t")]
    removed = [ln.split("\t",1)[1] for ln in diff_lines if ln.startswith("D\t")]

    return pull_out, install_out, added, modified, removed

async def deploy_to_screen(chat_id: int):
    """Sends deploy commands into the screen session."""
    cmds = [
        f"cd {PROJECT_PATH}",
        "git pull",
        f"{sys.executable} -m pip install -r requirements.txt"
    ]
    for cmd in cmds:
        packed = cmd + "\n"
        subprocess.call(["screen", "-S", SCREEN_SESSION, "-X", "stuff", packed])
    await bot.send_message(chat_id, f"🚀 Deployed latest into screen session '{SCREEN_SESSION}'.")

@dp.message(Command("update"))
async def update_handler(message: Message):
    status = await message.reply("🔄 Running update process…")
    try:
        pull_out, install_out, added, modified, removed = await run_update_process(message.chat.id)
        # Build summary text
        summary = [
            f"📥 Git Pull Output:\n```
{pull_out}
```",
            f"📦 Pip Install Output:\n```
{install_out}
```",
            "🗂️ Changes:",
        ]
        if added: summary.append(f"➕ Added: {', '.join(added)}")
        if modified: summary.append(f"✏️ Modified: {', '.join(modified)}")
        if removed: summary.append(f"❌ Removed: {', '.join(removed)}")
        text = "\n".join(summary)

        # Buttons
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🔄 Re-run Update", callback_data="update:run"),
            InlineKeyboardButton("📝 Show Diff", callback_data="update:diff"),
            InlineKeyboardButton("📡 Deploy to Screen", callback_data="update:deploy"),
        )

        await status.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        logger.exception("Update error")
        await status.edit_text(f"❌ Update failed: {e}")

@dp.callback_query(lambda c: c.data and c.data.startswith("update:"))
async def on_update_button(query: CallbackQuery):
    await query.answer()
    action = query.data.split(':',1)[1]
    chat_id = query.message.chat.id

    if action == "run":
        await update_handler(query.message)
    elif action == "diff":
        # simply re-run diff
        _, _, added, modified, removed = await run_update_process(chat_id)
        parts = []
        if added: parts.append(f"➕ Added: {', '.join(added)}")
        if modified: parts.append(f"✏️ Modified: {', '.join(modified)}")
        if removed: parts.append(f"❌ Removed: {', '.join(removed)}")
        await bot.send_message(chat_id, "\n".join(parts) or "No changes.")
    elif action == "deploy":
        await deploy_to_screen(chat_id)

@dp.startup
async def on_startup():
    global last_remote_sha
    # initialize last remote SHA
    try:
        out = subprocess.check_output(["git","ls-remote","origin","HEAD"]).decode().split()
        last_remote_sha = out[0].strip()
    except Exception:
        last_remote_sha = None
    # launch background task
    asyncio.create_task(check_for_updates())

async def check_for_updates():
    """Periodically checks remote and notifies admin if new commits."""
    global last_remote_sha
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        try:
            out = subprocess.check_output(["git","ls-remote","origin","HEAD"]).decode().split()
            remote_sha = out[0].strip()
            if last_remote_sha and remote_sha != last_remote_sha:
                last_remote_sha = remote_sha
                # notify admin
                if ADMIN_CHAT_ID:
                    kb = InlineKeyboardMarkup().add(
                        InlineKeyboardButton("🔄 Update Now", callback_data="update:run")
                    )
                    await bot.send_message(
                        ADMIN_CHAT_ID,
                        f"🆕 New update detected: {remote_sha[:7]}",
                        reply_markup=kb
                    )
        except Exception as e:
            logger.error(f"Failed remote check: {e}")
