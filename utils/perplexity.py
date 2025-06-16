import os
import requests

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

def perplexity_search(query, model="perplexity-search", max_results=10):
    """
    Performs a search using the Perplexity Pro Search API.
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
    except Exception as e:
        return f"[Perplexity Search API error: {e}]"
