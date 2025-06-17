import os
import requests

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

# Use current valid Sonar models from Perplexity docs (as of 2025)
SONAR_MODELS = {
    "small_chat": "sonar-small-chat",
    "medium_chat": "sonar-medium-chat",
    "large_chat": "sonar-large-chat",
    # Add online if it returns to docs, or use chat models only
}

# Default to the most capable model available
DEFAULT_SONAR_MODEL = SONAR_MODELS.get("large_chat", "sonar-medium-chat")

def deep_sonar(prompt, model=DEFAULT_SONAR_MODEL, system_prompt=None, max_tokens=1000, temperature=0.7, top_p=0.9):
    """
    Sends a prompt to a Sonar model via Perplexity API.
    Default model: sonar-large-chat.
    """
    if not PERPLEXITY_API_KEY:
        return "[Perplexity API key not set.]"
    permitted_models = set(SONAR_MODELS.values())
    if model not in permitted_models:
        return f"[Invalid Sonar model '{model}'. Permitted models: {', '.join(permitted_models)}.]"
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
        r = requests.post(url, headers=headers, json=data, timeout=60)
        r.raise_for_status()
        response = r.json()
        return response.get("choices", [{}])[0].get("message", {}).get("content", "[Empty response from Sonar.]")
    except requests.HTTPError as e:
        try:
            err_json = r.json()
            err_message = err_json.get("error", {}).get("message", "")
            return f"\nSonar API Error:\nStatus: {r.status_code}\nMessage: {err_message}\n"
        except Exception:
            return f"\nSonar API Error:\nStatus: {r.status_code}\nBody: {r.text}\n"
    except Exception as e:
        return f"[Sonar API error: {e}]"
