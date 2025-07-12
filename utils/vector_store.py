import os
import glob
import json
import hashlib
import asyncio
from typing import Dict, List, Callable, Any, Optional, Union, Tuple, Awaitable
import httpx
from pinecone import Pinecone, PineconeException, ServerlessSpec
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type, wait_exponential
import logging

# Конфигурация логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("vector_store")

# Пути и константы
VECTOR_META_PATH = "data/vector_store.meta.json"
EMBED_DIM = 1536  # Для OpenAI ada-002
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120
MAX_CONCURRENT_REQUESTS = 5  # Ограничение количества одновременных запросов

# Получаем переменные окружения
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "selesta-index")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "gcp-starter")

# Семафор для ограничения количества одновременных запросов к API
embed_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

def init_pinecone() -> Optional[Tuple[Pinecone, Any]]:
    """
    Инициализирует клиент Pinecone и возвращает его вместе с индексом.
    
    Returns:
        Optional[Tuple[Pinecone, Any]]: Клиент Pinecone и индекс или None при ошибке
    """
    if not PINECONE_API_KEY:
        logger.warning("PINECONE_API_KEY not set, vector store will not be available")
        return None
    
    try:
        # Инициализируем клиент Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        
        # Проверяем, существует ли индекс
        indexes = [x["name"] for x in pc.list_indexes()]
        
        # Создаем индекс, если его нет
        if PINECONE_INDEX not in indexes:
            logger.info(f"Creating Pinecone index: {PINECONE_INDEX}")
            pc.create_index(
                name=PINECONE_INDEX,
                dimension=EMBED_DIM,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-west-2"
                )
            )
        
        # Получаем объект индекса
        vector_index = pc.Index(PINECONE_INDEX)
        return pc, vector_index
    except Exception as e:
        logger.error(f"Failed to initialize Pinecone: {e}")
        return None

# Инициализируем Pinecone клиент и индекс
pinecone_client = init_pinecone()
pc = pinecone_client[0] if pinecone_client else None
vector_index = pinecone_client[1] if pinecone_client else None

def file_hash(fname: str) -> str:
    """
    Возвращает MD5 хеш заданного файла.
    
    Args:
        fname: Путь к файлу
        
    Returns:
        str: MD5 хеш содержимого файла
    """
    try:
        with open(fname, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        logger.error(f"Error hashing file {fname}: {e}")
        return ""

def scan_files(path_patterns: Union[str, List[str]] = ["config/*.md", "config/*.txt", "config/*.json"]) -> Dict[str, str]:
    """
    Сканирует файлы по заданным паттернам и возвращает словарь {имя_файла: md5_хеш}.
    
    Args:
        path_patterns: Строка или список строк с паттернами для glob
        
    Returns:
        Dict[str, str]: Словарь {имя_файла: md5_хеш}
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
    Загружает метаданные векторного хранилища из JSON.
    
    Returns:
        Dict[str, str]: Словарь метаданных {имя_файла: хеш}
    """
    try:
        # Создаем директорию, если она не существует
        os.makedirs(os.path.dirname(VECTOR_META_PATH), exist_ok=True)
        
        if os.path.isfile(VECTOR_META_PATH):
            with open(VECTOR_META_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in {VECTOR_META_PATH}, resetting meta file")
    except Exception as e:
        logger.error(f"Error loading vector meta: {e}")
    
    return {}

def save_vector_meta(meta: Dict[str, str]) -> None:
    """
    Сохраняет метаданные векторного хранилища в JSON.
    
    Args:
        meta: Словарь метаданных для сохранения
    """
    try:
        # Создаем директорию, если она не существует
        os.makedirs(os.path.dirname(VECTOR_META_PATH), exist_ok=True)
        
        with open(VECTOR_META_PATH, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving vector meta: {e}")

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
        # Если абзац слишком длинный, разбиваем его на части
        if len(paragraph) > chunk_size:
            # Сначала добавляем текущий чанк, если он не пустой
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            
            # Разбиваем длинный абзац
            for i in range(0, len(paragraph), chunk_size - overlap):
                part = paragraph[i:i + chunk_size]
                if part.strip() and len(part) >= min_chunk_size:
                    chunks.append(part)
        # Если добавление абзаца превысит размер чанка
        elif len(current_chunk) + len(paragraph) + 2 > chunk_size:
            # Добавляем текущий чанк
            if current_chunk and len(current_chunk) >= min_chunk_size:
                chunks.append(current_chunk)
            
            # Начинаем новый чанк
            current_chunk = paragraph
        else:
            # Добавляем абзац к текущему чанку
            if current_chunk:
                current_chunk += "\n\n" + paragraph
            else:
                current_chunk = paragraph
    
    # Добавляем последний чанк, если он не пустой
    if current_chunk and len(current_chunk) >= min_chunk_size:
        chunks.append(current_chunk)
    
    return chunks

async def vectorize_file(
    fname: str,
    openai_api_key: str,
    current_hash: str,
    on_message: Optional[Callable[[str], Any]] = None
) -> List[str]:
    """
    Векторизует отдельный файл и загружает его в Pinecone.
    
    Args:
        fname: Имя файла
        openai_api_key: API ключ OpenAI
        current_hash: Хеш файла
        on_message: Функция обратного вызова для сообщений
        
    Returns:
        List[str]: Список обработанных ID
    """
    if not vector_index:
        logger.warning("Pinecone index not available, skipping vectorization")
        return []
    
    upserted_ids = []
    try:
        with open(fname, "r", encoding="utf-8") as f:
            text = f.read()

        chunks = chunk_text(text)

        for idx, chunk in enumerate(chunks):
            meta_id = f"{fname}:{idx}"
            try:
                emb = await get_embedding(chunk, openai_api_key)
                vector_index.upsert(
                    vectors=[
                        {
                            "id": meta_id,
                            "values": emb,
                            "metadata": {"file": fname, "chunk": idx, "hash": current_hash},
                        }
                    ]
                )
                upserted_ids.append(meta_id)
                await call_callback(on_message, f"Upserted {meta_id}")
            except Exception as e:
                logger.error(f"Error upserting vector {meta_id}: {e}")
                await call_callback(on_message, f"Error upserting {meta_id}: {e}")
    except Exception as e:
        logger.error(f"Error vectorizing file {fname}: {e}")
        await call_callback(on_message, f"Error vectorizing file {fname}: {e}")
    
    return upserted_ids

async def vectorize_all_files(
    openai_api_key: str,
    force: bool = False,
    on_message: Optional[Callable[[str], Any]] = None,
    path_patterns: Union[str, List[str]] = ["config/*.md", "config/*.txt", "config/*.json"]
) -> Dict[str, List[str]]:
    """
    Векторизует все файлы в указанных директориях.
    Обновляет Pinecone индекс для новых/измененных файлов, удаляет для удаленных.
    
    Args:
        openai_api_key: API ключ OpenAI
        force: Принудительное обновление всех файлов
        on_message: Функция обратного вызова для сообщений
        path_patterns: Паттерны для поиска файлов
        
    Returns:
        Dict[str, List[str]]: Словарь с информацией об обработанных файлах
    """
    if not vector_index:
        logger.warning("Pinecone index not available, skipping vectorization")
        await call_callback(on_message, "Vector store not available (Pinecone not configured)")
        return {"upserted": [], "deleted": []}
    
    # Сканируем текущие файлы и загружаем предыдущие метаданные
    current = scan_files(path_patterns)
    previous = load_vector_meta()

    # Определяем измененные, новые и удаленные файлы
    changed = [f for f in current if (force or current[f] != previous.get(f))]
    new = [f for f in current if f not in previous]
    removed = [f for f in previous if f not in current]

    # Если нет изменений и не запрошено принудительное обновление, просто выходим
    if not changed and not new and not removed and not force:
        await call_callback(on_message, "Vector store already up to date")
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
    for fname in removed:
        # Предполагаем максимум 50 чанков на файл
        for idx in range(50):
            meta_id = f"{fname}:{idx}"
            try:
                vector_index.delete(ids=[meta_id])
                deleted_ids.append(meta_id)
                await call_callback(on_message, f"Deleted {meta_id}")
            except Exception:
                # Если ID не существует, просто продолжаем
                pass
    
    # Сохраняем обновленные метаданные
    save_vector_meta(current)
    
    # Отправляем итоговое сообщение
    summary = (
        f"Vectorization complete. "
        f"New/changed: {len(changed + new)} files, "
        f"Removed: {len(removed)} files, "
        f"Upserted: {len(upserted_ids)} chunks, "
        f"Deleted: {len(deleted_ids)} chunks."
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
    Выполняет семантический поиск по Pinecone индексу.
    Возвращает наиболее релевантные чанки.
    
    Args:
        query: Запрос для поиска
        openai_api_key: API ключ OpenAI
        top_k: Количество результатов для возврата
        min_score: Минимальный порог сходства
        
    Returns:
        List[str]: Список найденных чанков текста
    """
    if not vector_index:
        logger.warning("Pinecone index not available, skipping semantic search")
        return []
    
    chunks = []
    try:
        # Получаем эмбеддинг для запроса
        emb = await get_embedding(query, openai_api_key)
        
        # Выполняем поиск
        res = vector_index.query(
            vector=emb,
            top_k=top_k,
            include_metadata=True,
            include_values=False
        )
        
        # Обрабатываем результаты
        matches = getattr(res, "matches", [])
        for match in matches:
            score = match.get("score", 0)
            
            # Пропускаем результаты с низким сходством
            if score < min_score:
                continue
                
            metadata = match.get("metadata", {})
            fname = metadata.get("file")
            chunk_idx = metadata.get("chunk")
            
            # Получаем текст чанка из файла
            try:
                with open(fname, "r", encoding="utf-8") as f:
                    file_text = f.read()
                
                # Разбиваем файл на чанки и получаем нужный
                all_chunks = chunk_text(file_text)
                if chunk_idx is not None and 0 <= chunk_idx < len(all_chunks):
                    chunk_text_ = all_chunks[chunk_idx]
                    chunks.append(f"From {os.path.basename(fname)} (score: {score:.2f}):\n{chunk_text_}")
            except Exception as e:
                logger.error(f"Error retrieving chunk from {fname}: {e}")
    except Exception as e:
        logger.error(f"Error during semantic search: {e}")
    
    return chunks

async def is_vector_store_available() -> bool:
    """
    Проверяет доступность векторного хранилища.
    
    Returns:
        bool: True если хранилище доступно, False в противном случае
    """
    if not vector_index:
        return False
    
    try:
        # Пробуем выполнить простую операцию с индексом
        stats = vector_index.describe_index_stats()
        return True
    except Exception:
        return False
