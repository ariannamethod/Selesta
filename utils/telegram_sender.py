import os
import asyncio
import random
from typing import List, Tuple
import httpx

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def send_message(chat_id: str, text: str) -> bool:
    """Send a message via Telegram Bot API.

    Returns ``True`` on success, ``False`` otherwise so callers can
    react to delivery failures.
    """
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN not configured")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}

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

async def send_multipart_message(
    chat_id: str, parts: List[str], delay_range: Tuple[float, float] = (1.0, 2.0)
) -> bool:
    """Send multiple parts sequentially with optional delays.

    Returns ``True`` if all messages were delivered successfully.
    """
    success = True
    for part in parts:
        part_ok = await send_message(chat_id, part)
        success = success and part_ok
        await asyncio.sleep(
            delay_range[0]
            if delay_range[0] == delay_range[1]
            else random.uniform(*delay_range)
        )
    return success
