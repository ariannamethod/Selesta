import os
import asyncio
from pypdf import PdfReader
from docx import Document
from striprtf.striprtf import rtf_to_text
from bs4 import BeautifulSoup
import csv

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
        return "[PDF is empty or unreadable.]"
    except Exception as e:
        return f"[Error reading PDF ({os.path.basename(path)}): {e}]"

def extract_text_from_docx(path):
    try:
        doc = Document(path)
        text = "\n".join([p.text for p in doc.paragraphs])
        text = text.strip()
        return text[:MAX_TEXT_SIZE] + ('\n[Truncated]' if len(text) > MAX_TEXT_SIZE else '')
    except Exception as e:
        return f"[Error reading DOCX ({os.path.basename(path)}): {e}]"

def extract_text_from_txt(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return text[:MAX_TEXT_SIZE] + ('\n[Truncated]' if len(text) > MAX_TEXT_SIZE else '')
    except Exception as e:
        return f"[Error reading TXT ({os.path.basename(path)}): {e}]"

def extract_text_from_rtf(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = rtf_to_text(f.read())
        return text[:MAX_TEXT_SIZE] + ('\n[Truncated]' if len(text) > MAX_TEXT_SIZE else '')
    except Exception as e:
        return f"[Error reading RTF ({os.path.basename(path)}): {e}]"

def extract_text_from_odt(path):
    try:
        # Try odfpy first; fallback to textract if not available
        try:
            from odf.opendocument import load
            from odf.text import P
            doc = load(path)
            text = "\n".join([str(t) for t in doc.getElementsByType(P)])
            text = text.strip()
        except ImportError:
            try:
                import textract
                text = textract.process(path).decode("utf-8")
            except Exception as e:
                return f"[Error reading ODT ({os.path.basename(path)}): {e}]"
        return text[:MAX_TEXT_SIZE] + ('\n[Truncated]' if len(text) > MAX_TEXT_SIZE else '')
    except Exception as e:
        return f"[Error reading ODT ({os.path.basename(path)}): {e}]"

def extract_text_from_html(path):
    try:
        with open(path, encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
            text = soup.get_text(separator="\n")
        text = text.strip()
        return text[:MAX_TEXT_SIZE] + ('\n[Truncated]' if len(text) > MAX_TEXT_SIZE else '')
    except Exception as e:
        return f"[Error reading HTML ({os.path.basename(path)}): {e}]"

def extract_text_from_csv(path):
    try:
        with open(path, encoding="utf-8") as f:
            reader = csv.reader(f)
            text = "\n".join([", ".join(row) for row in reader])
        text = text.strip()
        return text[:MAX_TEXT_SIZE] + ('\n[Truncated]' if len(text) > MAX_TEXT_SIZE else '')
    except Exception as e:
        return f"[Error reading CSV ({os.path.basename(path)}): {e}]"

def extract_text_from_md(path):
    # Treat markdown as plain text
    return extract_text_from_txt(path)

def extract_text_from_doc(path):
    # Try using textract for legacy .doc files
    try:
        import textract
        text = textract.process(path).decode("utf-8")
        text = text.strip()
        return text[:MAX_TEXT_SIZE] + ('\n[Truncated]' if len(text) > MAX_TEXT_SIZE else '')
    except Exception as e:
        return f"[Error reading DOC ({os.path.basename(path)}): {e}]"

def extract_text_from_file(path):
    ext = os.path.splitext(path)[-1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(path)
    elif ext == ".docx":
        return extract_text_from_docx(path)
    elif ext == ".doc":
        return extract_text_from_doc(path)
    elif ext == ".txt":
        return extract_text_from_txt(path)
    elif ext == ".md":
        return extract_text_from_md(path)
    elif ext == ".rtf":
        return extract_text_from_rtf(path)
    elif ext == ".odt":
        return extract_text_from_odt(path)
    elif ext in [".html", ".htm"]:
        return extract_text_from_html(path)
    elif ext == ".csv":
        return extract_text_from_csv(path)
    else:
        return f"[Unsupported file type: {os.path.basename(path)}]"

async def extract_text_from_file_async(path):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, extract_text_from_file, path)
