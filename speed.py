import sys
import speedtest
from aiogram.filters import Command
from aiogram.types import Message
from SafoneAPI import SafoneAPI

# grab the dispatcher from main
_main = sys.modules["__main__"]
dp = _main.dp

api = SafoneAPI()

@dp.message(Command("speed"))
async def send_speed_via_ai(message: Message):
    status = await message.reply("⏳ Running speed test…")
    try:
        # 1) Run the speed test
        st = speedtest.Speedtest()
        st.get_best_server()
        download_mbps = st.download() / 1_000_000
        upload_mbps   = st.upload(pre_allocate=False) / 1_000_000
        ping_ms       = st.results.ping

        # 2) Build the prompt
        prompt = (
            "I just measured a server's network performance:\n"
            f"- Download: {download_mbps:.2f} Mbps\n"
            f"- Upload:   {upload_mbps:.2f} Mbps\n"
            f"- Ping:     {ping_ms:.2f} ms\n\n"
            "Write me a friendly, concise summary of these results and suggest what they imply "
            "about the server's suitability for tasks like web hosting, video streaming, and real-time gaming."
        )

        # 3) Ask ChatGPT via SafoneAPI
        resp = await api.chatgpt(prompt)
        summary = getattr(resp, "message", str(resp))

        # 4) Edit the original message with the AI summary
        await status.edit_text(summary)

    except Exception as e:
        await status.edit_text(f"⚠️ Speed+AI failed: {e}")
