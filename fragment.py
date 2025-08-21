# === Drop-in block: account registration checker for +888 / E.164 numbers ===
# Safe to paste after your existing imports; does not modify any routers/handlers.
from typing import List, Dict, Optional, Tuple
import asyncio
import os
import re
import logging

# Optional Telethon (MTProto) import to check phone registration status via contacts.importContacts
try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.errors import FloodWaitError, RpcError
    from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
    from telethon.tl.types import InputPhoneContact
except Exception:  # Telethon not installed or not available
    TelegramClient = None  # type: ignore

_TELETHON_CLIENT = None  # type: ignore
_TELETHON_LOCK = asyncio.Lock()

def _normalize_phone(num: str) -> str:
    # Keep digits/+; ensure + prefix; handle 888 numbers commonly shown without '+'
    s = re.sub(r'[^0-9+]', '', str(num))
    if s.startswith('+'):
        digits = '+' + re.sub(r'\D', '', s[1:])
    else:
        digits = re.sub(r'\D', '', s)
    if digits and not digits.startswith('+'):
        if digits.startswith('888'):
            digits = '+' + digits
        else:
            digits = '+' + digits
    return digits

async def _ensure_telethon_client() -> Optional["TelegramClient"]:
    """
    Creates/returns a logged-in Telethon client from env:
      MT_API_ID / MT_API_HASH and TG_STRING_SESSION
      (or a pre-authorized file session at TELETHON_SESSION_PATH)
    Returns None if Telethon is unavailable or not authorized.
    """
    global _TELETHON_CLIENT
    if _TELETHON_CLIENT is not None:
        return _TELETHON_CLIENT
    if TelegramClient is None:
        logging.warning("Telethon not installed; account connection checks will be skipped.")
        return None

    async with _TELETHON_LOCK:
        if _TELETHON_CLIENT is not None:
            return _TELETHON_CLIENT

        api_id = os.getenv('MT_API_ID') or os.getenv('TELEGRAM_API_ID') or os.getenv('API_ID')
        api_hash = os.getenv('MT_API_HASH') or os.getenv('TELEGRAM_API_HASH') or os.getenv('API_HASH')
        string_session = os.getenv('TG_STRING_SESSION') or os.getenv('TELETHON_STRING_SESSION')
        session_path = os.getenv('TELETHON_SESSION_PATH', '.tg_session')

        if not (api_id and api_hash):
            logging.warning("MT_API_ID / MT_API_HASH not set; skipping connection checks.")
            return None

        try:
            if string_session:
                client = TelegramClient(StringSession(string_session), int(api_id), api_hash)
            else:
                client = TelegramClient(session_path, int(api_id), api_hash)

            await client.connect()
            try:
                is_auth = await client.is_user_authorized()
            except TypeError:
                is_auth = client.is_user_authorized()  # type: ignore
            if not is_auth:
                logging.warning("Telethon session is not authorized. Provide TG_STRING_SESSION or a logged-in session file.")
                await client.disconnect()
                return None

            _TELETHON_CLIENT = client
            return _TELETHON_CLIENT
        except Exception as e:
            logging.exception("Failed to initialize Telethon client: %s", e)
            return None

async def check_numbers_connected(numbers: List[str]) -> Dict[str, Optional[bool]]:
    """
    Returns: dict number(str as seen in your text) -> True (connected), False (free), None (unknown).
    Uses MTProto contacts.importContacts (requires a logged-in Telethon *user* session).
    """
    sanitized: List[Tuple[str, str]] = []  # (orig, normalized)
    seen = set()
    for n in numbers:
        if not n: 
            continue
        orig = str(n).strip()
        norm = _normalize_phone(orig)
        if norm in seen:
            continue
        seen.add(norm)
        sanitized.append((orig, norm))

    if not sanitized:
        return {}

    client = await _ensure_telethon_client()
    if client is None:
        return {orig: None for (orig, _norm) in sanitized}

    results: Dict[str, Optional[bool]] = {orig: None for (orig, _norm) in sanitized}

    CHUNK = 50  # safe batch size
    for i in range(0, len(sanitized), CHUNK):
        chunk = sanitized[i:i+CHUNK]
        contacts = [InputPhoneContact(client_id=idx, phone=norm, first_name='.', last_name='')
                    for idx, (_orig, norm) in enumerate(chunk)]
        try:
            resp = await client(ImportContactsRequest(contacts=contacts))
            imported_ids = {ic.client_id for ic in getattr(resp, 'imported', [])}
            for idx, (orig, _norm) in enumerate(chunk):
                results[orig] = (idx in imported_ids)
            # Clean up to avoid polluting your address book
            try:
                if getattr(resp, 'users', None):
                    await client(DeleteContactsRequest(id=[u.id for u in resp.users]))
            except Exception:
                pass
        except FloodWaitError as fw:
            await asyncio.sleep(int(getattr(fw, 'seconds', 60)) + 1)
            # retry once for this chunk
            try:
                resp = await client(ImportContactsRequest(contacts=contacts))
                imported_ids = {ic.client_id for ic in getattr(resp, 'imported', [])}
                for idx, (orig, _norm) in enumerate(chunk):
                    results[orig] = (idx in imported_ids)
                try:
                    if getattr(resp, 'users', None):
                        await client(DeleteContactsRequest(id=[u.id for u in resp.users]))
                except Exception:
                    pass
            except Exception:
                for orig, _norm in chunk:
                    results[orig] = None
        except RpcError:
            for orig, _norm in chunk:
                results[orig] = None
        except Exception:
            for orig, _norm in chunk:
                results[orig] = None

    return results

async def augment_numbers_block(text: str) -> str:
    """
    Parse a block like:
        🔒 Restricted: 5/254
        1. 🔒 88801457239
        ...
    Append: ' — ✅ Free' or ' — ❌ connected to an account' (or ' — ⚠️ unknown') to each number line.
    Safe for both plain and HTML parse_mode.
    """
    if not text:
        return text
    lines = text.splitlines()
    # Pull out candidate numbers per line
    nums: List[str] = []
    for ln in lines:
        m = re.search(r'(\+?888\d{5,}|(?:\+?\d[\d\s\-]{6,}\d))', ln)
        if m:
            nums.append(m.group(1).replace(' ', '').replace('-', ''))

    status = await check_numbers_connected(nums)

    def decorate(ln: str) -> str:
        m = re.search(r'(\+?888\d{5,}|(?:\+?\d[\d\s\-]{6,}\d))', ln)
        if not m:
            return ln
        raw = m.group(1).replace(' ', '').replace('-', '')
        st = status.get(raw) or status.get(raw.lstrip('+')) or status.get('+' + raw)
        if "✅ Free" in ln or "❌" in ln or "⚠️" in ln:
            return ln  # avoid double-tagging
        if st is True:
            return ln + " — ❌ connected to an account"
        elif st is False:
            return ln + " — ✅ Free"
        else:
            return ln + " — ⚠️ unknown"

    return "\n".join(decorate(ln) for ln in lines)
# === End drop-in block ===
