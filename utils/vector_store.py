import os
import glob
import json
import hashlib
from typing import Dict, List, Callable, Any, Optional
from pinecone import Pinecone, PineconeException
import openai
from tenacity import retry, stop_after_attempt, wait_fixed

VECTOR_META_PATH = "vector_store.meta.json"
EMBED_DIM = 1536  # For OpenAI ada-002

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX")

# Initialize Pinecone client and index
pc = Pinecone(api_key=PINECONE_API_KEY)
if PINECONE_INDEX not in [x["name"] for x in pc.list_indexes()]:
    pc.create_index(name=PINECONE_INDEX, dimension=EMBED_DIM, metric="cosine")
vector_index = pc.Index(PINECONE_INDEX)

def file_hash(fname: str) -> str:
    """Returns an MD5 hash of the given file."""
    with open(fname, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def scan_files(path: str = "config/*.md") -> Dict[str, str]:
    """Scans for files in the given path, returns {filename: md5 hash}."""
    files = {}
    for fname in glob.glob(path):
        files[fname] = file_hash(fname)
    return files

def load_vector_meta() -> Dict[str, str]:
    """Loads vector store metadata from JSON."""
    if os.path.isfile(VECTOR_META_PATH):
        with open(VECTOR_META_PATH, "r") as f:
            return json.load(f)
    return {}

def save_vector_meta(meta: Dict[str, str]) -> None:
    """Saves vector store metadata to JSON."""
    with open(VECTOR_META_PATH, "w") as f:
        json.dump(meta, f)

@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
async def safe_embed(text: str, openai_api_key: str) -> List[float]:
    """Retries embedding up to 3 times on failure."""
    return await get_embedding(text, openai_api_key)

async def get_embedding(text: str, openai_api_key: str) -> List[float]:
    """Gets an embedding for the provided text using OpenAI."""
    openai.api_key = openai_api_key
    res = openai.embeddings.create(
        model="text-embedding-ada-002",
        input=text
    )
    return res.data[0].embedding

def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> List[str]:
    """Splits text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks

async def vectorize_all_files(
    openai_api_key: str,
    force: bool = False,
    on_message: Optional[Callable[[str], Any]] = None
) -> Dict[str, List[str]]:
    """
    Vectorizes all files in the config directory.
    Updates Pinecone index for new/changed files, deletes for removed files.
    """
    current = scan_files()
    previous = load_vector_meta()
    changed = [f for f in current if (force or current[f] != previous.get(f))]
    new = [f for f in current if f not in previous]
    removed = [f for f in previous if f not in current]

    upserted_ids = []
    for fname in current:
        if fname not in changed and fname not in new and not force:
            continue
        with open(fname, "r", encoding="utf-8") as f:
            text = f.read()
        chunks = chunk_text(text)
        for idx, chunk in enumerate(chunks):
            meta_id = f"{fname}:{idx}"
            try:
                emb = await safe_embed(chunk, openai_api_key)
                vector_index.upsert(vectors=[
                    {
                        "id": meta_id,
                        "values": emb,
                        "metadata": {"file": fname, "chunk": idx, "hash": current[fname]}
                    }
                ])
                upserted_ids.append(meta_id)
            except PineconeException as e:
                if on_message:
                    await on_message(f"Pinecone error: {e}")
                continue

    deleted_ids = []
    for fname in removed:
        for idx in range(50):
            meta_id = f"{fname}:{idx}"
            try:
                vector_index.delete(ids=[meta_id])
                deleted_ids.append(meta_id)
            except Exception:
                pass

    save_vector_meta(current)
    if on_message:
        await on_message(
            f"Vectorization complete. New/changed: {', '.join(changed + new) if changed or new else '-'}; removed: {', '.join(removed) if removed else '-'}"
        )
    return {"upserted": upserted_ids, "deleted": deleted_ids}

async def semantic_search(
    query: str,
    openai_api_key: str,
    top_k: int = 5
) -> List[str]:
    """
    Performs a semantic search over the Pinecone vector index.
    Returns the most relevant chunks.
    """
    emb = await safe_embed(query, openai_api_key)
    res = vector_index.query(vector=emb, top_k=top_k, include_metadata=True)
    chunks = []
    matches = getattr(res, "matches", [])
    for match in matches:
        metadata = match.get("metadata", {})
        fname = metadata.get("file")
        chunk_idx = metadata.get("chunk")
        try:
            with open(fname, "r", encoding="utf-8") as f:
                all_chunks = chunk_text(f.read())
                chunk_text_ = all_chunks[chunk_idx] if chunk_idx is not None and chunk_idx < len(all_chunks) else ""
        except Exception:
            chunk_text_ = ""
        if chunk_text_:
            chunks.append(chunk_text_)
    return chunks
