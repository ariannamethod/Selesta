import os
import httpx
from typing import Any, Dict, Union

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

# Use the correct default model: "pplx-70b-online" or "pplx-70b-chat" if "perplexity-search" is not supported
DEFAULT_MODEL = "pplx-70b-online"

async def perplexity_search(
    query: str,
    model: str = DEFAULT_MODEL,
    max_results: int = 10
) -> Union[Dict[str, Any], str]:
    """
    Performs a search using the Perplexity API (async).
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
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            try:
                result = response.json()
                # Check for API-specific error structure
                if isinstance(result, dict) and "error" in result:
                    err_message = result["error"].get("message") or str(result["error"])
                    return f"[Perplexity Search API error: {err_message}]"
                return result
            except Exception:
                return f"[Perplexity Search: Response decode error]"
    except httpx.HTTPStatusError as e:
        try:
            err_json = e.response.json()
            err_message = err_json.get("error", {}).get("message", "")
            return f"[Perplexity Search API error: {err_message}]"
        except Exception:
            return f"[Perplexity Search API error: HTTP {e.response.status_code} - {e.response.text}]"
    except Exception as e:
        return f"[Perplexity Search API error: {e}]"
