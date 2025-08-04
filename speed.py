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
        # 1) Run the speedtest (this will block—consider moving to an executor for production)
        st = speedtest.Speedtest()
        st.get_best_server()
        download_mbps = st.download() / 1_000_000
        upload_mbps   = st.upload(pre_allocate=False) / 1_000_000
        ping_ms       = st.results.ping

        # 2) Build an AI prompt
        prompt = (
            f\"\"\"I just measured a server's network performance:
- Download: {download_mbps:.2f} Mbps
- Upload:   {upload_mbps:.2f} Mbps
- Ping:     {ping_ms:.2f} ms

Write me a friendly, concise summary of these results and suggest what they imply about the server's suitability
for tasks like web hosting, video streaming, and real-time gaming.\"\"\"
        )

        # 3) Send to SafoneAPI (ChatGPT)
        resp = await api.chatgpt(prompt)
        summary = getattr(resp, "message", str(resp))

        # 4) Edit the original message with AI-generated summary
        await status.edit_text(summary)

    except Exception as e:
        await status.edit_text(f"⚠️ Speed+AI failed: {e}")
