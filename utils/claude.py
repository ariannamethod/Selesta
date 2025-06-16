import os
import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

def ask_claude(prompt, model="claude-3-opus-20240229", max_tokens=1024):
    """
    Sends a prompt to Claude via Anthropic API and returns the response text.
    """
    if not ANTHROPIC_API_KEY:
        return "[Claude API key not set.]"
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    data = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(url, headers=headers, json=data)
            response.raise_for_status()
            resp_json = response.json()
            return resp_json.get("content", [{}])[0].get("text", "[Empty response from Claude.]")
    except Exception as e:
        return f"[Claude API error: {e}]"
