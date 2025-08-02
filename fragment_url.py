import sys
import re
from aiogram import F, types
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

# Grab bot & dispatcher from main
_main = sys.modules["__main__"]
dp    = _main.dp
bot   = _main.bot

def format_fragment_url(raw: str) -> str:
    # strip non-digits, remove leading zeros
    num = re.sub(r"\D+", "", raw).lstrip("0")
    if not num.startswith("888"):
        num = "888" + num
    return f"https://fragment.com/number/{num}/code"

@dp.inline_query(F.query.regexp(r".*"))
async def inline_fragment(inline_query: types.InlineQuery):
    raw     = inline_query.query.strip()
    cleaned = re.sub(r"\s+", "", raw).lstrip("+")
    if not cleaned.isdigit():
        # ignore non-numeric queries
        return

    url = format_fragment_url(cleaned)
    result = InlineQueryResultArticle(
        id=cleaned,  # must be a unique string ≤64 chars
        title=f"Fragment URL → {cleaned}",
        description=url,
        input_message_content=InputTextMessageContent(
            message_text=url
        )
    )

    # Answer the inline query
    await inline_query.answer(results=[result], cache_time=30)
