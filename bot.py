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
```python
def send_logs_as_file(chat_id: int, pull_out: str, install_out: str):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
    tmp.write("=== Git Pull Output ===\n")
    tmp.write(pull_out + "\n\n")
    tmp.write("=== Pip Install Output ===\n")
    tmp.write(install_out + "\n")
    tmp.close()
    return bot.send_document(chat_id, FSInputFile(tmp.name), caption="📄 Full update logs")
```

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
        "-X", "stuff", "\x03"   # Ctrl-C
    ])

    # 2) In-session update & reinstall
    cmds = [
        f"cd {PROJECT_PATH}",
        "git pull",
        f"{sys.executable} -m pip install -r requirements.txt",
        f"{sys.executable} {os.path.join(PROJECT_PATH,'bot.py')}"
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
