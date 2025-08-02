#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Uses the unofficial Fragment JSON client (vendored under vendor/userapi)
  • Fetches sale listings and reports the first +888 number’s TON & USD price
"""

import os
import sys
import logging
from aiogram.filters import Command
from aiogram.types import Message

# 1) Make sure Python can import the vendored code
ROOT   = os.path.dirname(__file__)
VENDOR = os.path.join(ROOT, "vendor", "userapi")
if VENDOR not in sys.path:
    sys.path.insert(0, VENDOR)

# 2) Now import the real FragmentClient
from userapi import FragmentClient

# grab dispatcher & bot from main
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        client = FragmentClient()
        data   = await client.get_numbers(filter="sale")
        if not data or not getattr(data, "nodes", None):
            raise ValueError("No sale listings found")

        first  = data.nodes[0]
        number = first.number
        ton    = first.assetPrice.value
        usd    = first.fiatPrice

        await status.delete()
        await message.answer(
            f"💰 Current Floor Number: +{number}\n\n"
            f"• Price: {ton} TON (~${usd})"
        )

    except Exception as e:
        logger.exception("floor error")
        await status.edit_text(f"❌ Failed to fetch floor: {e}")
