
# bot_corrected.py (replaces chatgpt_handler with toggle logic)

# ─── ChatGPT toggle state ──────────────────────────────────────────
chatgpt_enabled: dict[int, bool] = {}

# ─── /act & /actnot Commands ────────────────────────────────────────
@dp.message(Command("act"))
async def activate_chatgpt(message: Message):
    if message.chat.type != "private":
        return await message.reply("🤖 /act only applies in a private chat.")
    uid = message.from_user.id
    chatgpt_enabled[uid] = True
    await message.reply("✅ ChatGPT fallback is now ON for your DMs.")

@dp.message(Command("actnot"))
async def deactivate_chatgpt(message: Message):
    if message.chat.type != "private":
        return await message.reply("🤖 /actnot only applies in a private chat.")
    uid = message.from_user.id
    chatgpt_enabled[uid] = False
    await message.reply("❌ ChatGPT fallback is now OFF for your DMs.")

# ─── Adjusted ChatGPT Fallback ─────────────────────────────────────
@dp.message(F.text & ~F.text.startswith("/"))
async def chatgpt_handler(message: Message):
    if message.chat.type != "private":
        return
    if not chatgpt_enabled.get(message.from_user.id, False):
        return
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
