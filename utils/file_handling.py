import os
from pypdf import PdfReader
import asyncio

def extract_text_from_pdf(path):
    try:
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
        return text.strip() if text.strip() else '[PDF пустой или нечитабельный]'
    except Exception as e:
        return f"[PDF read error in {os.path.basename(path)}: {e}]"

def extract_text_from_txt(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"[TXT read error in {os.path.basename(path)}: {e}]"

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
