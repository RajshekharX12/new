#!/usr/bin/env python3
import os
import sys
import html
import logging
import subprocess
import asyncio

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
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
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp  = Dispatcher()

# ─── SAFONEAPI CLIENT ─────────────────────────────────────────────
api = SafoneAPI()

# ─── PLUGINS & HANDLERS ──────────────────────────────────────────
import fragment_url   # inline 888 → fragment.com URL
import speed          # /speed VPS speedtest
import review         # /review code quality + /help
import floor          # /888 current floor price

@dp.message(F.text & ~F.text.startswith("/"))
async def chatgpt_handler(message: types.Message):
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

# ─── UPDATE & AUTO-DEPLOY LOGIC ──────────────────────────────────
last_remote_sha = None

async def run_update_process() -> tuple[str, str, list[str], list[str], list[str]]:
    old_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    pull_out = subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT).decode().strip()
    try:
        install_out = subprocess.check_output(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            stderr=subprocess.STDOUT
        ).decode().strip()
    except subprocess.CalledProcessError as e:
        install_out = f"ERROR: {e.output.decode().strip()}"

    new_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    diff_lines = subprocess.check_output(
        ["git", "diff", "--name-status", old_sha, new_sha],
        stderr=subprocess.STDOUT
    ).decode().splitlines()

    added    = [ln.split("\t",1)[1] for ln in diff_lines if ln.startswith("A\t")]
    modified = [ln.split("\t",1)[1] for ln in diff_lines if ln.startswith("M\t")]
    removed  = [ln.split("\t",1)[1] for ln in diff_lines if ln.startswith("D\t")]
    return pull_out, install_out, added, modified, removed

async def deploy_to_screen(chat_id: int):
    cmds = [
        f"cd {PROJECT_PATH}",
        "git pull",
        f"{sys.executable} -m pip install -r requirements.txt",
    ]
    for cmd in cmds:
        subprocess.call(["screen", "-S", SCREEN_SESSION, "-X", "stuff", cmd + "\n"])
    await bot.send_message(chat_id, f"🚀 Deployed into screen session “{SCREEN_SESSION}”")

@dp.message(Command("update"))
async def update_handler(message: Message):
    status = await message.reply("🔄 Running update…")
    try:
        pull_out, install_out, added, modified, removed = await run_update_process()
        summary = [
            f"""📥 Git Pull Output:
