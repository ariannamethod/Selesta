import os
import asyncio
from typing import Optional

import httpx
from gtts import gTTS
from pydub import AudioSegment
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
        audio_file = open(file_path, "rb")
        transcript = await openai.Audio.atranscribe("whisper-1", audio_file)
        return transcript.get("text", "")
    except Exception as e:
        print(f"Whisper transcription error: {e}")
        return ""

async def text_to_speech(text: str, output_path: str) -> str:
    """Convert text to speech and save to ``output_path``."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _sync_tts, text, output_path)
    return output_path

def _sync_tts(text: str, output_path: str) -> None:
    tts = gTTS(text)
    tts.save(output_path)
    # ensure it is valid mp3
    AudioSegment.from_file(output_path).export(output_path, format="mp3")
