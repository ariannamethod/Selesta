import difflib
import requests
from bs4 import BeautifulSoup

def fuzzy_match(a: str, b: str) -> float:
    """Return the similarity ratio between two strings using difflib."""
    return difflib.SequenceMatcher(None, a, b).ratio()

def extract_text_from_url(url: str) -> str:
    """
    Extracts readable text content from the given URL.
    Removes scripts, styles, headers, footers, navigation, and asides.
    Returns up to 3500 characters.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Selesta Agent)"}
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for s in soup(["script", "style", "header", "footer", "nav", "aside"]):
            s.decompose()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        result = "\n".join(lines)[:3500]
        return result
    except Exception as e:
        return f"[Error loading page: {e}]"
