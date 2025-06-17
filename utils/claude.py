import os
import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CREATOR_CHAT_ID = os.getenv("CREATOR_CHAT_ID")

def _strip_claude_intro(text: str) -> str:
    """
    Removes Claude's standard greeting if present.
    """
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
    If Claude returns a standard greeting or is empty, this reply is stripped or replaced by a gentle silence (💎).
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
            content_blocks = resp_json.get("content", [])
            text = ""
            for block in content_blocks:
                if isinstance(block, dict):
                    text += block.get("text", "")
                elif isinstance(block, str):
                    text += block
            text = _strip_claude_intro(text)
            # Claude sometimes outputs nothing or a canned message; filter it out
            if not text or text.strip() in {
                "[Empty response from Claude.]", 
                "I'm sorry, but I don't have enough information to answer that.",
                "I'm sorry, but I can't help with that.",
                "I'm sorry, but I must remain silent on this topic."
            }:
                text = "💎"
            if notify_creator:
                print(f"Oleg, main engine failed. Claude fallback active. Notified at {CREATOR_CHAT_ID}.")
            return text.strip()
    except Exception as e:
        return "💎"
