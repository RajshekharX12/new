import sys
import logging

try:
    import speedtest
except ImportError:
    raise RuntimeError("Please install speedtest-cli: pip install speedtest-cli")

from aiogram.filters import Command
from aiogram.types import Message

# grab the dispatcher from main
_main = sys.modules["__main__"]
dp = _main.dp
logger = logging.getLogger(__name__)

@dp.message(Command(commands=["speed"]))
async def send_speed(message: Message):
    st = speedtest.Speedtest()
    try:
        st.get_best_server()
        download_bps = st.download()
        upload_bps = st.upload(pre_allocate=False)
        download_mbps = download_bps / 1_000_000
        upload_mbps = upload_bps / 1_000_000
        ping = st.results.ping

        reply = (
            "📶 VPS Speed Test Results:\n"
            f"• Download: {download_mbps:.2f} Mbps\n"
            f"• Upload: {upload_mbps:.2f} Mbps\n"
            f"• Ping: {ping:.2f} ms"
        )
    except Exception as e:
        logger.exception("Speed test failed")
        reply = f"⚠️ Speed test failed: {e}"

    await message.answer(reply)
