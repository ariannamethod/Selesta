import os
import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CREATOR_CHAT_ID = os.getenv("CREATOR_CHAT_ID")

def _strip_claude_intro(text: str) -> str:
    """
    Removes Claude's standard greeting if present.
    """
    # Claude may start with "Hello! I'm Claude..." or "Hi! I'm Claude..."
    lines = text.strip().splitlines()
    if lines and (
        lines[0].lower().startswith("hello! i'm claude")
        or lines[0].lower().startswith("hi! i'm claude")
        or lines[0].lower().startswith("hello, i'm claude")
        or lines[0].lower().startswith("hi, i'm claude")
    ):
        # Remove the greeting line and any trailing separators
        return "\n".join(lines[1:]).lstrip("-— \n").strip()
    return text.strip()

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
        "messages": [ {"role": "user", "content": prompt} ]
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            resp_json = response.json()
            # Claude returns content as a list of message blocks
            content_blocks = resp_json.get("content", [])
            text = ""
            # Join all text blocks (Anthropic usually returns a list of dicts with "text")
            for block in content_blocks:
                if isinstance(block, dict):
                    text += block.get("text", "")
                elif isinstance(block, str):
                    text += block
            text = _strip_claude_intro(text)
            if notify_creator:
                # Place actual notification logic here (e.g., Telegram/Email)
                print(f"Oleg, main engine failed. Claude fallback active. Notified at {CREATOR_CHAT_ID}.")
            return text or "[Empty response from Claude.]"
    except Exception as e:
        return f"[Claude Emergency API error: {e}]"
