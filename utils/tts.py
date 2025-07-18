import os
import asyncio
import httpx
from typing import Optional

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TTS_MODEL = "tts-1"

async def generate_speech_async(text: str, output_path: str, voice: str = "alloy") -> bool:
    """Generate speech audio from text using OpenAI's TTS API."""
    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY not configured")
        return False
    try:
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": TTS_MODEL, "input": text, "voice": voice}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post("https://api.openai.com/v1/audio/speech", headers=headers, json=payload)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(response.content)
        return True
    except Exception as e:
        print(f"Error generating speech: {e}")
        return False

def generate_speech(text: str, output_path: str, voice: str = "alloy") -> bool:
    """Synchronous wrapper for generate_speech_async."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(generate_speech_async(text, output_path, voice))
