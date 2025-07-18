import os
from typing import Optional

import httpx
import openai

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

async def download_telegram_file(file_id: str, dest_path: str) -> Optional[str]:
    """Download a file from Telegram and save it locally."""
    if not TELEGRAM_TOKEN:
        print("TELEGRAM_TOKEN not configured")
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile",
                params={"file_id": file_id},
            )
            resp.raise_for_status()
            file_path = resp.json().get("result", {}).get("file_path")
            if not file_path:
                return None
            file_url = (
                f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
            )
            file_resp = await client.get(file_url)
            file_resp.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(file_resp.content)
            return dest_path
    except Exception as e:
        print(f"Error downloading telegram file: {e}")
        return None

async def transcribe_audio(file_path: str) -> str:
    """Transcribe audio using OpenAI Whisper."""
    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY not configured")
        return ""
    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        with open(file_path, "rb") as audio_file:
            resp = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        return getattr(resp, "text", "")
    except Exception as e:
        print(f"Whisper transcription error: {e}")
        return ""

async def text_to_speech(text: str, output_path: str) -> str:
    """Convert text to speech and save to ``output_path`` using OpenAI TTS."""
    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY not configured")
        return ""

    try:
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        async with client.audio.speech.with_streaming_response.create(
            model="tts-1",
            voice="alloy",
            input=text,
        ) as resp:
            await resp.stream_to_file(output_path)
        return output_path
    except Exception as e:
        print(f"TTS error: {e}")
        return ""
