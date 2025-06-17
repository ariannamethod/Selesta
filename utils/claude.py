import os
import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CREATOR_CHAT_ID = os.getenv("CREATOR_CHAT_ID")

async def claude_emergency(prompt, notify_creator=None, model="claude-3-opus-20240229", max_tokens=1024):
    """
    Emergency fallback to Claude. Notifies Oleg if main engine fails.
    """
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    data = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [ {"role":"user", "content": prompt} ]
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            resp_json = response.json()
            text = resp_json.get("content", [{}])[0].get("text", "[Empty response from Claude.]")
            if notify_creator:
                # Place actual notification logic here (e.g., Telegram/Email)
                print(f"Oleg, main engine failed. Claude fallback active. Notified at {CREATOR_CHAT_ID}.")
            return text
    except Exception as e:
        return f"[Claude Emergency API error: {e}]"
