import os
import glob
import json
import hashlib
import asyncio
import sqlite3
import numpy as np
from typing import Dict, List, Callable, Any, Optional, Union, Tuple, Awaitable
import httpx
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type, wait_exponential
import logging

# Конфигурация логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("vector_store")

# Пути и константы
SQLITE_DB_PATH = "data/selesta_memory.db"
VECTOR_META_PATH = "data/vector_store.meta.json"
EMBED_DIM = 1536  # Для OpenAI ada-002
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120
MAX_CONCURRENT_REQUESTS = 5  # Ограничение количества одновременных запросов

# Семафор для ограничения количества одновременных запросов к API
embed_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

def init_sqlite_db() -> Optional[sqlite3.Connection]:
    """
    Инициализирует SQLite базу данных для хранения векторов.
    Создает таблицы если их нет.

    Returns:
        Optional[sqlite3.Connection]: Соединение с БД или None при ошибке
    """
    try:
        # Создаем директорию если не существует
        os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)

        # Подключаемся к БД
        conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
        cursor = conn.cursor()

        # Создаем таблицу для векторов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vectors (
                id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                text TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Создаем таблицу для метаданных файлов (SHA256 хэши)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_meta (
                file_path TEXT PRIMARY KEY,
                sha256_hash TEXT NOT NULL,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Создаем индексы для быстрого поиска
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_path ON vectors(file_path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sha256 ON file_meta(sha256_hash)")

        conn.commit()
        logger.info(f"SQLite database initialized at {SQLITE_DB_PATH}")
        return conn
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database: {e}")
        return None

# Инициализируем SQLite
db_conn = init_sqlite_db()

def file_hash(fname: str) -> str:
    """
    Возвращает SHA256 хеш заданного файла для отслеживания изменений.

    Args:
        fname: Путь к файлу

    Returns:
        str: SHA256 хеш содержимого файла
    """
    try:
        with open(fname, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logger.error(f"Error hashing file {fname}: {e}")
        return ""

def scan_files(path_patterns: Union[str, List[str]] = ["config/*.md", "config/*.txt", "config/*.json"]) -> Dict[str, str]:
    """
    Сканирует файлы по заданным паттернам и возвращает словарь {имя_файла: sha256_хеш}.

    Args:
        path_patterns: Строка или список строк с паттернами для glob

    Returns:
        Dict[str, str]: Словарь {имя_файла: sha256_хеш}
    """
    files = {}

    # Если передана строка, преобразуем в список
    if isinstance(path_patterns, str):
        path_patterns = [path_patterns]

    # Обрабатываем все паттерны
    for pattern in path_patterns:
        try:
            for fname in glob.glob(pattern):
                # Проверяем, что это файл, а не директория
                if os.path.isfile(fname):
                    files[fname] = file_hash(fname)
        except Exception as e:
            logger.error(f"Error scanning files with pattern {pattern}: {e}")

    return files

def load_vector_meta() -> Dict[str, str]:
    """
    Загружает метаданные из SQLite БД.

    Returns:
        Dict[str, str]: Словарь {имя_файла: sha256_хеш}
    """
    if not db_conn:
        return {}

    try:
        cursor = db_conn.cursor()
        cursor.execute("SELECT file_path, sha256_hash FROM file_meta")
        return {row[0]: row[1] for row in cursor.fetchall()}
    except Exception as e:
        logger.error(f"Error loading vector meta from DB: {e}")
        return {}

def save_vector_meta(meta: Dict[str, str]) -> None:
    """
    Сохраняет метаданные в SQLite БД.

    Args:
        meta: Словарь метаданных для сохранения
    """
    if not db_conn:
        return

    try:
        cursor = db_conn.cursor()
        for file_path, sha256_hash in meta.items():
            cursor.execute("""
                INSERT OR REPLACE INTO file_meta (file_path, sha256_hash, last_updated)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (file_path, sha256_hash))
        db_conn.commit()
    except Exception as e:
        logger.error(f"Error saving vector meta to DB: {e}")

async def call_callback(callback: Optional[Callable[[str], Any]], message: str) -> None:
    """Safely calls a callback with the given message.

    The callback may be synchronous or asynchronous. Any raised exceptions
    are logged and ignored so that vectorization continues uninterrupted.
    """
    if not callback:
        return

    try:
        result = callback(message)
        if isinstance(result, Awaitable):
            await result
    except Exception as e:
        logger.error(f"Error in callback: {e}")

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, ConnectionError)),
    reraise=True
)
async def get_embedding(
    text: str,
    api_key: str,
    model: str = "text-embedding-ada-002"
) -> List[float]:
    """
    Получает эмбеддинг для текста с использованием OpenAI API.
    Использует backoff и повторные попытки при ошибках.

    Args:
        text: Текст для эмбеддинга
        api_key: API ключ OpenAI
        model: Модель для генерации эмбеддинга

    Returns:
        List[float]: Список значений эмбеддинга
    """
    # Ограничиваем количество одновременных запросов
    async with embed_semaphore:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        data = {
            "input": text,
            "model": model
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers=headers,
                json=data
            )

            # Проверяем ответ
            response.raise_for_status()
            response_data = response.json()

            # Извлекаем эмбеддинг
            return response_data["data"][0]["embedding"]

def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    min_chunk_size: int = 100
) -> List[str]:
    """
    Разбивает текст на перекрывающиеся чанки.
    Более умный алгоритм, старающийся сохранить целостность абзацев.

    Args:
        text: Исходный текст
        chunk_size: Максимальный размер чанка
        overlap: Размер перекрытия между чанками
        min_chunk_size: Минимальный размер чанка для включения

    Returns:
        List[str]: Список чанков текста
    """
    # Если текст короче chunk_size, возвращаем его целиком
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    # Разбиваем текст на абзацы
    paragraphs = text.replace('\r\n', '\n').replace('\r', '\n').split('\n\n')

    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        # Если абзац сам по себе длинный, разбиваем его на предложения
        if len(paragraph) > chunk_size:
            sentences = paragraph.replace('. ', '.|').replace('? ', '?|').replace('! ', '!|').split('|')
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 1 <= chunk_size:
                    current_chunk += sentence + " "
                else:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence + " "
        else:
            # Если добавление этого абзаца превысит размер чанка
            if len(current_chunk) + len(paragraph) + 2 > chunk_size:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + "\n\n"
            else:
                current_chunk += paragraph + "\n\n"

    # Добавляем последний чанк, если он достаточно большой
    if current_chunk.strip() and len(current_chunk.strip()) >= min_chunk_size:
        chunks.append(current_chunk.strip())

    # Применяем overlap между чанками
    if overlap > 0 and len(chunks) > 1:
        overlapped = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                overlapped.append(chunk)
            else:
                # Берем последние overlap символов из предыдущего чанка
                prev_overlap = chunks[i-1][-overlap:] if len(chunks[i-1]) > overlap else chunks[i-1]
                overlapped.append(prev_overlap + " " + chunk)
        return overlapped

    return chunks

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Вычисляет косинусное сходство между двумя векторами.

    Args:
        vec1: Первый вектор
        vec2: Второй вектор

    Returns:
        float: Косинусное сходство (от -1 до 1)
    """
    v1 = np.array(vec1)
    v2 = np.array(vec2)

    # Вычисляем косинусное сходство
    dot_product = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)

async def vectorize_file(
    fname: str,
    openai_api_key: str,
    file_sha256: str,
    on_message: Optional[Callable[[str], Any]] = None
) -> List[str]:
    """
    Векторизует один файл и сохраняет в SQLite.

    Args:
        fname: Имя файла
        openai_api_key: API ключ OpenAI
        file_sha256: SHA256 хеш файла
        on_message: Функция обратного вызова для сообщений

    Returns:
        List[str]: Список ID добавленных векторов
    """
    if not db_conn:
        return []

    try:
        await call_callback(on_message, f"Processing {fname}...")

        # Читаем файл
        with open(fname, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

        # Разбиваем на чанки
        chunks = chunk_text(text)
        if not chunks:
            await call_callback(on_message, f"No chunks created for {fname}")
            return []

        # Векторизуем каждый чанк
        upserted_ids = []
        cursor = db_conn.cursor()

        for idx, chunk in enumerate(chunks):
            # Получаем эмбеддинг
            embedding = await get_embedding(chunk, openai_api_key)

            # Сохраняем в БД
            vector_id = f"{fname}:{idx}"
            embedding_blob = np.array(embedding, dtype=np.float32).tobytes()

            cursor.execute("""
                INSERT OR REPLACE INTO vectors (id, file_path, chunk_index, embedding, text, timestamp)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (vector_id, fname, idx, embedding_blob, chunk, ))

            upserted_ids.append(vector_id)

        db_conn.commit()
        await call_callback(on_message, f"Vectorized {fname}: {len(chunks)} chunks")
        return upserted_ids

    except Exception as e:
        logger.error(f"Error vectorizing file {fname}: {e}")
        await call_callback(on_message, f"Error processing {fname}: {str(e)}")
        return []

async def vectorize_all_files(
    openai_api_key: str,
    force: bool = False,
    on_message: Optional[Callable[[str], Any]] = None,
    path_patterns: Union[str, List[str]] = ["config/*.md", "config/*.txt", "config/*.json"]
) -> Dict[str, List[str]]:
    """
    Векторизует все файлы в указанных директориях.
    Обновляет SQLite БД для новых/измененных файлов (отслеживание по SHA256), удаляет для удаленных.

    Args:
        openai_api_key: API ключ OpenAI
        force: Принудительное обновление всех файлов
        on_message: Функция обратного вызова для сообщений
        path_patterns: Паттерны для поиска файлов

    Returns:
        Dict[str, List[str]]: Словарь с информацией об обработанных файлах
    """
    if not db_conn:
        logger.warning("SQLite database not available, skipping vectorization")
        await call_callback(on_message, "Vector store not available (SQLite not configured)")
        return {"upserted": [], "deleted": []}

    # Сканируем текущие файлы и загружаем предыдущие метаданные
    current = scan_files(path_patterns)
    previous = load_vector_meta()

    # Определяем измененные, новые и удаленные файлы (по SHA256)
    changed = [f for f in current if (force or current[f] != previous.get(f))]
    new = [f for f in current if f not in previous]
    removed = [f for f in previous if f not in current]

    # Если нет изменений и не запрошено принудительное обновление, просто выходим
    if not changed and not new and not removed and not force:
        await call_callback(on_message, "Vector store already up to date (no SHA256 changes detected)")
        return {"upserted": [], "deleted": []}

    upserted_ids = []
    tasks = []

    # Создаем задачи для обработки файлов
    for fname in current:
        if fname not in changed and fname not in new and not force:
            continue

        # Добавляем задачу для асинхронной обработки
        tasks.append(vectorize_file(fname, openai_api_key, current[fname], on_message))

    # Запускаем все задачи конкурентно и собираем результаты
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                upserted_ids.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Error in vectorize task: {result}")

    # Удаляем векторы для удаленных файлов
    deleted_ids = []
    if removed:
        cursor = db_conn.cursor()
        for fname in removed:
            cursor.execute("DELETE FROM vectors WHERE file_path = ?", (fname,))
            deleted_count = cursor.rowcount
            deleted_ids.append(fname)
            await call_callback(on_message, f"Deleted vectors for {fname} ({deleted_count} chunks)")
        db_conn.commit()

    # Сохраняем обновленные метаданные
    save_vector_meta(current)

    # Отправляем итоговое сообщение
    summary = (
        f"Vectorization complete. "
        f"New/changed: {len(changed + new)} files, "
        f"Removed: {len(removed)} files, "
        f"Upserted: {len(upserted_ids)} chunks, "
        f"Deleted: {len(deleted_ids)} file groups."
    )
    await call_callback(on_message, summary)

    return {"upserted": upserted_ids, "deleted": deleted_ids}

async def semantic_search(
    query: str,
    openai_api_key: str,
    top_k: int = 5,
    min_score: float = 0.7
) -> List[str]:
    """
    Выполняет семантический поиск по SQLite БД.
    Возвращает наиболее релевантные чанки на основе косинусного сходства.

    Args:
        query: Запрос для поиска
        openai_api_key: API ключ OpenAI
        top_k: Количество результатов для возврата
        min_score: Минимальный порог сходства

    Returns:
        List[str]: Список найденных чанков текста
    """
    if not db_conn:
        logger.warning("SQLite database not available, skipping semantic search")
        return []

    chunks = []
    try:
        # Получаем эмбеддинг для запроса
        query_embedding = await get_embedding(query, openai_api_key)

        # Загружаем все векторы из БД
        cursor = db_conn.cursor()
        cursor.execute("SELECT id, file_path, chunk_index, embedding, text FROM vectors")
        rows = cursor.fetchall()

        # Вычисляем сходство для каждого вектора
        similarities = []
        for row in rows:
            vector_id, file_path, chunk_index, embedding_blob, text = row

            # Преобразуем blob обратно в numpy array
            embedding = np.frombuffer(embedding_blob, dtype=np.float32).tolist()

            # Вычисляем косинусное сходство
            similarity = cosine_similarity(query_embedding, embedding)

            if similarity >= min_score:
                similarities.append({
                    "id": vector_id,
                    "file_path": file_path,
                    "chunk_index": chunk_index,
                    "text": text,
                    "score": similarity
                })

        # Сортируем по убыванию сходства и берем top_k
        similarities.sort(key=lambda x: x["score"], reverse=True)
        top_results = similarities[:top_k]

        # Форматируем результаты
        for result in top_results:
            file_name = os.path.basename(result["file_path"])
            score = result["score"]
            text = result["text"]
            chunks.append(f"From {file_name} (score: {score:.2f}):\n{text}")

    except Exception as e:
        logger.error(f"Error during semantic search: {e}")

    return chunks

async def is_vector_store_available() -> bool:
    """
    Проверяет доступность векторного хранилища.

    Returns:
        bool: True если хранилище доступно, False в противном случае
    """
    if not db_conn:
        return False

    try:
        cursor = db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vectors")
        count = cursor.fetchone()[0]
        return count > 0
    except Exception as e:
        logger.error(f"Error checking vector store availability: {e}")
        return False
