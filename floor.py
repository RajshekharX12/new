#!/usr/bin/env python3
"""
floor.py

Handler for /888:
  • Gives the direct link to Fragment’s sale page, where you can see the current floor price.
"""

import logging
from aiogram.filters import Command
from aiogram.types import Message

# grab dispatcher & bot from main
import sys
_main = sys.modules["__main__"]
dp    = _main.dp

logger = logging.getLogger(__name__)

@dp.message(Command(commands=["888"]))
async def floor_handler(message: Message):
    try:
        await message.reply(
            "🔗 You can view the current +888 floor price here:\n"
            "https://fragment.com/numbers?filter=sale"
        )
    except Exception:
        logger.exception("floor link error")
        await message.reply("❌ Unable to provide floor link right now.")
