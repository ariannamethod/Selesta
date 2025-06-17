import os
import httpx
from typing import Optional

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

# Актуальные модели Sonar (2025)
SONAR_MODELS = {
    "small_chat": "sonar-small-chat",
    "medium_chat": "sonar-medium-chat",
    "large_chat": "sonar-large-chat",
}

# Лучше medium по дефолту
DEFAULT_SONAR_MODEL = SONAR_MODELS.get("medium_chat", "sonar-medium-chat")

async def deep_sonar(
    prompt: str,
    model: str = DEFAULT_SONAR_MODEL,
    system_prompt: Optional[str] = None,
    max_tokens: int = 1000,
    temperature: float = 0.7,
    top_p: float = 0.9
) -> str:
    """
    Sends a prompt to a Perplexity Sonar model via their async API.
    Returns the model's response text, or a formatted error.
    """
    if not PERPLEXITY_API_KEY:
        return "⚠️ [Perplexity API key not set.]"
    permitted_models = set(SONAR_MODELS.values())
    if model not in permitted_models:
        return f"⚠️ [Invalid Sonar model '{model}'. Permitted models: {', '.join(permitted_models)}.]"
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Selesta/1.0 (Resonance AI)",
        "Accept-Encoding": "gzip"
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt[:3500]})
    messages.append({"role": "user", "content": prompt})
    data = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            resp_json = response.json()
            result = resp_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not result or result.strip() in ("[Empty response from Sonar.]", ""):
                return "🔮"
            return result.strip()
    except httpx.HTTPStatusError as e:
        try:
            err_json = e.response.json()
            err_message = err_json.get("error", {}).get("message", "")
            return f"⚠️ Sonar API Error: {err_message or e.response.text}"
        except Exception:
            return f"⚠️ Sonar API Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"⚠️ Sonar API error: {e}"
