import os
import requests

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

def perplexity_search(query, model="perplexity-search", max_results=10):
    """
    Performs a search using the Perplexity Pro Search API.
    Returns the JSON response or an English error message.
    """
    if not PERPLEXITY_API_KEY:
        return "[Perplexity API key not set.]"
    url = "https://api.perplexity.ai/search"
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Selesta/1.0 (Resonance AI)",
        "Accept-Encoding": "gzip"
    }
    data = {
        "model": model,
        "query": query,
        "max_results": max_results
    }
    try:
        r = requests.post(url, headers=headers, json=data, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        try:
            err_json = r.json()
            err_message = err_json.get("error", {}).get("message", "")
            return f"[Perplexity Search API error: {err_message}]"
        except Exception:
            return f"[Perplexity Search API error: HTTP {r.status_code} - {r.text}]"
    except Exception as e:
        return f"[Perplexity Search API error: {e}]"
