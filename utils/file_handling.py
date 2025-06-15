import os
from pypdf import PdfReader
import asyncio

MAX_TEXT_SIZE = 100_000  # Maximum number of characters per file

def extract_text_from_pdf(path):
    """
    Extracts text from a PDF file, limited to MAX_TEXT_SIZE characters.
    """
    try:
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
        text = text.strip()
        if text:
            return text[:MAX_TEXT_SIZE] + ('\n[Truncated]' if len(text) > MAX_TEXT_SIZE else '')
        return '[PDF is empty or unreadable.]'
    except Exception as e:
        return f"[PDF read error ({os.path.basename(path)}): {e}]"

def extract_text_from_txt(path):
    """
    Extracts text from a TXT or MD file, limited to MAX_TEXT_SIZE characters.
    """
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return text[:MAX_TEXT_SIZE] + ('\n[Truncated]' if len(text) > MAX_TEXT_SIZE else '')
    except Exception as e:
        return f"[TXT read error ({os.path.basename(path)}): {e}]"

def extract_text_from_file(path):
    """
    Extracts text from a file (PDF, TXT, or MD). Returns an error message for unsupported formats.
    """
    ext = os.path.splitext(path)[-1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(path)
    elif ext in [".txt", ".md"]:
        return extract_text_from_txt(path)
    else:
        return f"[Unsupported file type: {os.path.basename(path)}]"

async def extract_text_from_file_async(path):
    """
    Asynchronously extracts text from a file.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, extract_text_from_file, path)
