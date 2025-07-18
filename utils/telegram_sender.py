import os
import asyncio
import random
from typing import List, Tuple
import httpx

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def send_message(chat_id: str, text: str) -> None:
    """Send a message via Telegram Bot API."""
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN not configured")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=payload)
        except Exception as e:
            print(f"Error sending Telegram message: {e}")

async def send_multipart_message(
    chat_id: str, parts: List[str], delay_range: Tuple[float, float] = (1.0, 2.0)
) -> None:
    """Send multiple parts sequentially with optional delays."""
    for part in parts:
        await send_message(chat_id, part)
        await asyncio.sleep(
            delay_range[0]
            if delay_range[0] == delay_range[1]
            else random.uniform(*delay_range)
        )

async def send_voice(chat_id: str, file_path: str) -> None:
    """Send a voice message via Telegram Bot API."""
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN not configured")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVoice"
    async with httpx.AsyncClient() as client:
        try:
            with open(file_path, "rb") as f:
                await client.post(url, data={"chat_id": chat_id}, files={"voice": f})
        except Exception as e:
            print(f"Error sending Telegram voice: {e}")
