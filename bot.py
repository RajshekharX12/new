#!/usr/bin/env python3
import os
import sys
import html
import logging
import subprocess
import asyncio
import tempfile

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile,
)

from SafoneAPI import SafoneAPI

# ─── LOAD ENV & CONFIG ────────────────────────────────────────────
load_dotenv()
BOT_TOKEN             = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")

SCREEN_SESSION        = os.getenv("SCREEN_SESSION", "meow")
ADMIN_CHAT_ID         = int(os.getenv("ADMIN_CHAT_ID", "0"))
UPDATE_CHECK_INTERVAL = int(os.getenv("UPDATE_CHECK_INTERVAL", "3600"))
PROJECT_PATH          = os.getenv("PROJECT_PATH", os.getcwd())

# ─── LOGGING ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ─── BOT & DISPATCHER ─────────────────────────────────────────────
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ─── SAFONEAPI CLIENT ─────────────────────────────────────────────
api = SafoneAPI()

# ─── PLUGINS & FALLBACK ───────────────────────────────────────────
import fragment_url   # inline 888 → fragment.com URL
import speed          # /speed VPS speedtest
import review         # /review code quality + /help
import floor          # /888 current floor price

# ─── HELPERS ──────────────────────────────────────────────────────
def send_logs_as_file(chat_id: int, pull_out: str, install_out: str):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
    tmp.write("=== Git Pull Output ===\n")
    tmp.write(pull_out + "\n\n")
    tmp.write("=== Pip Install Output ===\n")
    tmp.write(install_out + "\n")
    tmp.close()
    return bot.send_document(chat_id, FSInputFile(tmp.name), caption="📄 Full update logs")

# ─── UPDATE & AUTO-DEPLOY LOGIC ──────────────────────────────────
last_remote_sha = None

async def run_update_process() -> tuple[str, str, list[str], list[str], list[str]]:
    old_sha   = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    pull_out  = subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT).decode().strip()
    try:
        install_out = subprocess.check_output(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            stderr=subprocess.STDOUT
        ).decode().strip()
    except subprocess.CalledProcessError as e:
        install_out = f"ERROR: {e.output.decode().strip()}"

    new_sha    = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    diff_lines = subprocess.check_output(
        ["git", "diff", "--name-status", old_sha, new_sha],
        stderr=subprocess.STDOUT
    ).decode().splitlines()

    added    = [ln.split("\t",1)[1] for ln in diff_lines if ln.startswith("A\t")]
    modified = [ln.split("\t",1)[1] for ln in diff_lines if ln.startswith("M\t")]
    removed  = [ln.split("\t",1)[1] for ln in diff_lines if ln.startswith("D\t")]

    return pull_out, install_out, added, modified, removed

async def deploy_to_screen(chat_id: int):
    """
    In-place restart inside the existing 'meow' screen session:
    - Send Ctrl-C to stop the old bot
    - Pull & reinstall
    - Relaunch bot.py in the same session
    """
    # 1) Stop running bot in session
    subprocess.call([
        "screen", "-S", SCREEN_SESSION,
        "-X", "stuff", "\x03",  # Ctrl-C
    ])

    # 2) In-session update & reinstall
    cmds = [
        f"cd {PROJECT_PATH}",
        "git pull",
        f"{sys.executable} -m pip install -r requirements.txt",
        f"{sys.executable} {os.path.join(PROJECT_PATH, 'bot.py')}"
    ]
    for cmd in cmds:
        subprocess.call([
            "screen", "-S", SCREEN_SESSION,
            "-X", "stuff", cmd + "\n"
        ])

    await bot.send_message(
        chat_id,
        f"🚀 Updated and restarted bot in existing '{SCREEN_SESSION}' session."
    )

@dp.message(F.text & ~F.text.startswith("/"))
async def chatgpt_handler(message: Message):
    text = message.text.strip()
    if not text:
        return
    try:
        resp = await api.chatgpt(text)
        answer = getattr(resp, "message", None) or str(resp)
        await message.answer(html.escape(answer))
    except Exception:
        logger.exception("chatgpt error")
        await message.reply("🚨 Error: SafoneAPI failed or no response.")

@dp.message(Command("update"))
async def update_handler(message: Message):
    status = await message.reply("🔄 Running update…")
    try:
        pull_out, install_out, added, modified, removed = await run_update_process()

        parts = ["🗂️ <b>Update Summary</b>:"]
        parts.append(
            "• Git pull: <code>OK</code>" 
            if "Already up to date." not in pull_out 
            else "• Git pull: <code>No changes</code>"
        )
        parts.append(
            "• Dependencies: <code>Installed</code>" 
            if "ERROR" not in install_out 
            else "• Dependencies: <code>Error</code>"
        )
        if added:
            parts.append(f"➕ Added: {', '.join(added)}")
        if modified:
            parts.append(f"✏️ Modified: {', '.join(modified)}")
        if removed:
            parts.append(f"❌ Removed: {', '.join(removed)}")
        text = "\n".join(parts)

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📄 View Full Logs", callback_data="update:logs"),
                    InlineKeyboardButton(text="📡 Deploy to Screen", callback_data="update:deploy"),
                ],
            ]
        )

        await status.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.exception("Update error")
        await status.edit_text(
            f"❌ Update failed:\n<code>{html.escape(str(e))}</code>",
            parse_mode="HTML"
        )

@dp.callback_query(lambda c: c.data and c.data.startswith("update:"))
async def on_update_button(query: CallbackQuery):
    await query.answer()
    action = query.data.split(":", 1)[1]
    chat_id = query.message.chat.id

    if action == "logs":
        pull_out, install_out, *_ = await run_update_process()
        await send_logs_as_file(chat_id, pull_out, install_out)
    elif action == "deploy":
        await deploy_to_screen(chat_id)

@dp.startup()
async def on_startup():
    global last_remote_sha
    try:
        out = subprocess.check_output(["git", "ls-remote", "origin", "HEAD"]).decode().split()
        last_remote_sha = out[0].strip()
    except Exception:
        last_remote_sha = None
    asyncio.create_task(check_for_updates())

async def check_for_updates():
    global last_remote_sha
    while True:
        await asyncio.sleep(UPDATE_CHECK_INTERVAL)
        try:
            out = subprocess.check_output(["git", "ls-remote", "origin", "HEAD"]).decode().split()
            remote_sha = out[0].strip()
            if last_remote_sha and remote_sha != last_remote_sha and ADMIN_CHAT_ID:
                last_remote_sha = remote_sha
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="🔄 Update Now", callback_data="update:run")]]
                )
                await bot.send_message(
                    ADMIN_CHAT_ID,
                    f"🆕 New update detected: <code>{remote_sha[:7]}</code>",
                    parse_mode="HTML",
                    reply_markup=kb
                )
        except Exception as e:
            logger.error(f"Failed remote check: {e}")

# ─── RUN BOT ───────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("🚀 Bot is starting…")
    dp.run_polling(bot)
