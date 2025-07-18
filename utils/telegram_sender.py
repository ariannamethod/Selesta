import os
import asyncio
import random
from typing import List, Tuple, Optional
import httpx

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def send_message(
    chat_id: str,
    text: str,
    reply_to_message_id: Optional[int] = None,
) -> bool:
    """Send a message via Telegram Bot API.

    Returns ``True`` on success, ``False`` otherwise so callers can
    react to delivery failures.
    """
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN not configured")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            print(
                f"Telegram API error {e.response.status_code}: {e.response.text}"
            )
        except Exception as e:
            print(f"Error sending Telegram message: {e}")
    return False

async def send_typing(chat_id: str) -> bool:
    """Send a 'typing' action to indicate response preparation."""
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN not configured")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction"
    payload = {"chat_id": chat_id, "action": "typing"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Error sending typing action: {e}")
    return False

async def send_audio_message(
    chat_id: str,
    audio_path: str,
    caption: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
) -> bool:
    """Send an audio file via Telegram."""
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN not configured")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendAudio"
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    if reply_to_message_id is not None:
        data["reply_to_message_id"] = reply_to_message_id

    async with httpx.AsyncClient() as client:
        try:
            with open(audio_path, "rb") as af:
                files = {"audio": af}
                response = await client.post(url, data=data, files=files)
                response.raise_for_status()
                return True
        except Exception as e:
            print(f"Error sending audio message: {e}")
    return False

async def send_multipart_message(
    chat_id: str,
    parts: List[str],
    delay_range: Tuple[float, float] = (5.0, 30.0),
    reply_to_message_id: Optional[int] = None,
) -> bool:
    """Send multiple parts sequentially with optional delays.

    Returns ``True`` if all messages were delivered successfully.
    """
    success = True
    for part in parts:
        part_ok = await send_message(chat_id, part, reply_to_message_id)
        success = success and part_ok
        await asyncio.sleep(
            delay_range[0]
            if delay_range[0] == delay_range[1]
            else random.uniform(*delay_range)
        )
    return success
