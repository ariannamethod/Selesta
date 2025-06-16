import os
from pypdf import PdfReader
import asyncio

MAX_TEXT_SIZE = 100_000  # Maximum number of characters for a single file

def extract_text_from_pdf(path):
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
        return f'[PDF is empty or unreadable.]'
    except Exception as e:
        return f"[Error reading PDF ({os.path.basename(path)}): {e}]"

def extract_text_from_txt(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return text[:MAX_TEXT_SIZE] + ('\n[Truncated]' if len(text) > MAX_TEXT_SIZE else '')
    except Exception as e:
        return f"[Error reading TXT ({os.path.basename(path)}): {e}]"

def extract_text_from_file(path):
    ext = os.path.splitext(path)[-1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(path)
    elif ext in [".txt", ".md"]:
        return extract_text_from_txt(path)
    else:
        return f"[Unsupported file type: {os.path.basename(path)}]"

async def extract_text_from_file_async(path):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, extract_text_from_file, path)
