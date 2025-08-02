#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Uses the Unofficial Fragment API (userapi) to fetch sale listings
  • Grabs the first +888 number, its TON price & USD equivalent
"""

import sys
import logging
from aiogram.filters import Command
from aiogram.types import Message
from vendor.userapi import FragmentClient
 # the unofficial wrapper

# grab dispatcher from main
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    status = await message.reply("🔍 Fetching current floor price…")
    try:
        client = FragmentClient()
        # fetch all “for sale” numbers
        data = await client.get_numbers(filter="sale")
        if not data or not data.nodes:
            raise ValueError("No sale listings found")

        first = data.nodes[0]
        number = first.number             # e.g. "88804686913"
        ton    = first.assetPrice.value   # e.g. 720
        usd    = first.fiatPrice          # e.g. 2602

        await status.delete()
        await message.answer(
            f"💰 Current Floor Number: +{number}\n\n"
            f"• Price: {ton} TON (~${usd})"
        )

    except Exception as e:
        logger.exception("floor error")
        await status.edit_text(f"❌ Failed to fetch floor: {e}")
