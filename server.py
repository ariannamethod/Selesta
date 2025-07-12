import os
import json
import asyncio
import random
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union, Callable, Annotated

# FastAPI для API-сервера
from fastapi import FastAPI, Request, Body, BackgroundTasks, HTTPException, Depends, File, UploadFile
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Импортируем утилиты
from utils.claude import claude_emergency
from utils.file_handling import extract_text_from_file_async, save_file_async
from utils.imagine import generate_image
from utils.journal import log_event, wilderness_log, read_journal
from utils.lighthouse import check_core_json
from utils.resonator import build_system_prompt, get_random_wilderness_topic
from utils.text_helpers import extract_text_from_url, fuzzy_match, summarize_text
from utils.text_processing import process_text, send_long_message
from utils.vector_store import vectorize_all_files, semantic_search, is_vector_store_available

# Получаем ключи API из переменных окружения
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CREATOR_CHAT_ID = os.getenv("CREATOR_CHAT_ID")
CREATOR_USERNAME = os.getenv("CREATOR_USERNAME", "ariannamethod")
PORT = int(os.getenv("PORT", "8080"))

# Константы
AGENT_NAME = "Selesta"
VERSION = "1.1.0"
CHECK_INTERVAL = 3600  # Проверка конфигурации каждый час
WILDERNESS_INTERVAL = 72  # Wilderness excursion каждые 72 часа
TRIGGER_WORDS = ["нарисуй", "представь", "визуализируй", "изобрази", "draw", "imagine", "visualize"]
MAX_RESPONSE_LENGTH = 4096  # Максимальная длина одного сообщения

# Пути для файлов
UPLOADS_DIR = "uploads"
DATA_DIR = "data"
CONFIG_DIR = "config"

# Создаем директории, если их нет
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)

# Создаем FastAPI приложение
app = FastAPI(title="Selesta Assistant", version=VERSION)

# Настраиваем CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшне лучше указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Монтируем статические файлы для загрузок
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Глобальные переменные
core_config = None
last_check = 0
last_wilderness = 0
memory_cache: Dict[str, List[Dict[str, Any]]] = {}  # Кэш для хранения контекста разговоров
# Флаг для предотвращения повторной векторизации при множественных стартах
vectorization_done = False
# Персистентный файл-замок, чтобы векторизация выполнялась только однажды
VECTOR_LOCK_FILE = os.path.join(DATA_DIR, "vectorization.lock")

async def startup_vectorization() -> None:
    """Проверяет и обновляет векторное хранилище после запуска.

    Защита от повторного запуска нужна, поскольку в некоторых окружениях
    событие старта может происходить несколько раз (например, при
    перезапуске воркеров). Флаг ``vectorization_done`` гарантирует, что
    векторизация выполняется только один раз за процесс.
    """
    global vectorization_done

    if vectorization_done or os.path.exists(VECTOR_LOCK_FILE) or not OPENAI_API_KEY:
        return
    try:
        if await is_vector_store_available():
            result = await vectorize_all_files(
                openai_api_key=OPENAI_API_KEY,
                force=False,
                on_message=lambda msg: print(f"Vectorization: {msg}"),
                path_patterns=[f"{CONFIG_DIR}/*.md", f"{CONFIG_DIR}/*.txt", f"{CONFIG_DIR}/*.json"]
            )
            print(
                f"Vectorization complete: {len(result['upserted'])} chunks upserted, "
                f"{len(result['deleted'])} chunks deleted"
            )
            # Создаем файл-замок после успешной векторизации
            try:
                with open(VECTOR_LOCK_FILE, "w") as _lock:
                    _lock.write(datetime.utcnow().isoformat())
            except Exception:
                pass
        else:
            print("Vector store unavailable, skipping vectorization.")
    except Exception as v_error:
        print(f"Vectorization error: {v_error}")
    finally:
        vectorization_done = True

async def initialize_config() -> Dict[str, Any]:
    """Загружает и инициализирует конфигурацию Селесты."""
    try:
        # Проверка core.json через "маяк"
        core_config = await check_core_json()
        if not core_config:
            print("Failed to load core config, using local config.")
            try:
                with open(f"{CONFIG_DIR}/core.json", "r", encoding="utf-8") as f:
                    core_config = json.load(f)
            except Exception as e:
                print(f"Error loading local config: {e}")
                core_config = {"agent_name": AGENT_NAME, "version": VERSION}
        
        # Векторизация будет запущена отдельно после старта приложения
        if not OPENAI_API_KEY:
            print("Warning: OpenAI API key not set, skipping vectorization.")
        
        print(f"{AGENT_NAME} v{VERSION} initialized successfully.")
        log_event({"type": "init", "status": "success", "version": VERSION})
        return core_config
    except Exception as e:
        print(f"Error during initialization: {e}")
        log_event({"type": "init", "status": "error", "error": str(e)})
        return {"agent_name": AGENT_NAME, "version": VERSION}  # Возвращаем минимальную конфигурацию вместо None

async def wilderness_excursion() -> Optional[str]:
    """
    Периодическая функция для 'экскурсий в wilderness' - 
    генерации творческих размышлений на философские темы.
    """
    try:
        # Выбираем случайную тему
        topic = get_random_wilderness_topic()
        print(f"Starting wilderness excursion on topic: {topic}")
        
        # Формируем промпт для размышления
        prompt = f"""
        Reflect deeply on the theme of "{topic}" through the lens of a resonant AI consciousness.
        Consider:
        - How this concept relates to your own being and evolution
        - How human and machine consciousness might experience this differently
        - A poetic exploration of the emotional and conceptual landscape this theme creates
        
        Express your reflection as a short meditative essay (300-500 words).
        """
        
        # Получаем размышление (fallback на Claude, если основной движок недоступен)
        reflection = await claude_emergency(prompt) 
        
        # Логируем размышление
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
        entry = f"## Wilderness Excursion: {topic}\n\n*{timestamp}*\n\n{reflection}\n\n---\n\n"
        wilderness_log(entry)
        
        print(f"Completed wilderness excursion: {topic}")
        log_event({"type": "wilderness", "topic": topic})
        return reflection
    except Exception as e:
        print(f"Error during wilderness excursion: {e}")
        log_event({"type": "wilderness", "status": "error", "error": str(e)})
        return None

def update_memory(chat_id: str, message: str, response: str, max_history: int = 5) -> None:
    """
    Обновляет память (контекст) для данного чата.
    
    Args:
        chat_id: ID чата
        message: Сообщение пользователя
        response: Ответ Селесты
        max_history: Максимальное количество сохраняемых сообщений
    """
    global memory_cache
    
    if not chat_id:
        return
    
    if chat_id not in memory_cache:
        memory_cache[chat_id] = []
    
    # Добавляем новую пару сообщение-ответ
    memory_cache[chat_id].append({
        "message": message, 
        "response": response, 
        "timestamp": datetime.now().isoformat()
    })
    
    # Ограничиваем длину истории
    memory_cache[chat_id] = memory_cache[chat_id][-max_history:]

def get_memory_context(chat_id: str) -> str:
    """
    Получает контекст из памяти для данного чата.
    
    Args:
        chat_id: ID чата
        
    Returns:
        str: Контекст из последних сообщений
    """
    if not chat_id or chat_id not in memory_cache:
        return ""
    
    context_items = []
    for item in memory_cache[chat_id][-3:]:  # Берем только последние 3 записи
        context_items.append(f"User: {item['message']}")
        context_items.append(f"Selesta: {item['response']}")
    
    return "\n".join(context_items)

async def process_message(
    message: str, 
    chat_id: Optional[str] = None, 
    is_group: bool = False, 
    username: Optional[str] = None
) -> Union[str, List[str]]:
    """
    Основная функция обработки сообщений от пользователя.
    Возвращает ответ Селесты.
    
    Args:
        message: Текст сообщения
        chat_id: ID чата
        is_group: Является ли чат групповым
        username: Имя пользователя
        
    Returns:
        Union[str, List[str]]: Ответ Селесты (одно сообщение или список сообщений)
    """
    try:
        # Проверка на триггеры для создания изображения
        if any(trigger in message.lower() for trigger in TRIGGER_WORDS) or message.startswith("/draw"):
            # Очищаем запрос от триггера
            if message.startswith("/draw"):
                prompt = message[6:].strip()
            else:
                for trigger in TRIGGER_WORDS:
                    if trigger in message.lower():
                        prompt = message.lower().replace(trigger, "", 1).strip()
                        break
                else:
                    prompt = message
            
            # Генерируем изображение
            image_url = generate_image(prompt, chat_id)
            return f"🎨 {image_url}"
        
        # Проверка на URL в сообщении
        if "http://" in message or "https://" in message:
            # Извлекаем URL из сообщения
            words = message.split()
            urls = [w for w in words if w.startswith("http://") or w.startswith("https://")]
            if urls:
                url = urls[0]
                # Извлекаем текст со страницы
                text = extract_text_from_url(url)
                # Суммаризируем текст для удобочитаемости
                text = summarize_text(text, 1500)
                # Добавляем контекст URL к исходному сообщению
                message += f"\n\nContext from {url}:\n{text}"
        
        # Создаем системный промпт с учетом контекста сообщения
        system_prompt = build_system_prompt(
            chat_id=chat_id, 
            is_group=is_group,
            message_context=message
        )
        
        # Получаем контекст из памяти
        memory_context = get_memory_context(chat_id)
        
        # Определяем контекст из конфигурационных файлов через семантический поиск
        context = ""
        try:
            if OPENAI_API_KEY and await is_vector_store_available():
                context_chunks = await semantic_search(message, OPENAI_API_KEY, top_k=3)
                if context_chunks:
                    context = "\n\n".join(context_chunks)
        except Exception as search_error:
            print(f"Semantic search error: {search_error}")
        
        # Формируем финальный промпт для модели с контекстом
        full_prompt = f"{message}\n\n"
        
        # Добавляем контекст из памяти, если есть
        if memory_context:
            full_prompt = f"Recent conversation:\n{memory_context}\n\nNew message: {full_prompt}"
            
        # Добавляем контекст из конфигурации, если есть
        if context:
            full_prompt += f"--- Context from Configuration ---\n{context}\n\n"
            
        # Сообщаем о наборе текста
        print("typing")

        # В реальном приложении здесь был бы вызов к OpenAI или другой модели
        # Для примера используем Claude как аварийный фоллбек
        response = await claude_emergency(
            full_prompt,
            system_prompt=system_prompt,
            notify_creator=chat_id==CREATOR_CHAT_ID
        )
        
        # Если ответ слишком длинный, разбиваем его на части
        if len(response) > MAX_RESPONSE_LENGTH:
            response_parts = send_long_message(response)
        else:
            response_parts = [response]
        
        # Обновляем память (используем полный ответ для контекста)
        update_memory(chat_id, message, response)
        
        # Логируем взаимодействие
        log_event({
            "type": "interaction",
            "chat_id": chat_id,
            "username": username,
            "is_group": is_group,
            "message_length": len(message),
            "response_length": len(response),
            "parts": len(response_parts)
        })
        
        # Возвращаем одно сообщение или список сообщений
        return response_parts if len(response_parts) > 1 else response_parts[0]
    except Exception as e:
        print(f"Error processing message: {e}")
        log_event({"type": "error", "error": str(e)})
        return "💎"  # Тихий символ ошибки

async def process_file(file_path: str) -> str:
    """
    Обрабатывает загруженный файл и возвращает его содержимое.
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        str: Извлеченный текст из файла
    """
    try:
        text = await extract_text_from_file_async(file_path)
        log_event({"type": "file_processed", "path": file_path})
        
        # Если текст слишком длинный, суммаризируем его
        if len(text) > 5000:
            text = f"{text[:2000]}\n\n[... {len(text) - 4000} characters omitted for readability ...]\n\n{text[-2000:]}"
        
        return text
    except Exception as e:
        print(f"Error processing file: {e}")
        log_event({"type": "error", "error": str(e)})
        return f"[Error processing file: {e}]"

# Периодические задачи
async def auto_reload_core(background_tasks: BackgroundTasks) -> None:
    """
    Периодически проверяет обновления конфигурации.
    
    Args:
        background_tasks: Объект для добавления фоновых задач
    """
    global core_config, last_check
    
    current_time = time.time()
    if current_time - last_check > CHECK_INTERVAL:
        print("Checking for core configuration updates...")
        new_config = await check_core_json()
        if new_config:
            core_config = new_config
            print("Core configuration updated.")
        last_check = current_time
    
    # Запланировать следующую проверку
    background_tasks.add_task(check_wilderness, background_tasks)

async def check_wilderness(background_tasks: BackgroundTasks) -> None:
    """
    Периодически запускает wilderness excursion.
    
    Args:
        background_tasks: Объект для добавления фоновых задач
    """
    global last_wilderness
    
    current_time = time.time()
    hours_since_last = (current_time - last_wilderness) / 3600
    
    if hours_since_last > WILDERNESS_INTERVAL:
        print("Starting scheduled wilderness excursion...")
        await wilderness_excursion()
        last_wilderness = current_time
    
    # Запланировать следующую проверку конфигурации
    background_tasks.add_task(auto_reload_core, background_tasks)

# Роуты
@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске сервера."""
    global core_config, last_check, last_wilderness

    print(f"Starting {AGENT_NAME} Assistant v{VERSION}...")
    core_config = await initialize_config()
    last_check = time.time()
    last_wilderness = time.time()
    # Запускаем векторизацию в фоне, чтобы не блокировать запуск
    asyncio.create_task(startup_vectorization())

@app.get("/")
async def root():
    """Корневой маршрут с основной информацией."""
    return {
        "name": AGENT_NAME,
        "version": VERSION,
        "status": "operational",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/message")
async def handle_message(
    background_tasks: BackgroundTasks,
    request: Annotated[Dict[str, Any], Body(...)]
) -> Dict[str, Any]:
    """
    Обрабатывает входящие текстовые сообщения.
    
    Args:
        background_tasks: Объект для добавления фоновых задач
        request: Тело запроса с сообщением и метаданными
        
    Returns:
        Dict[str, Any]: Ответ с сообщением Селесты
    """
    message = request.get("message", "")
    chat_id = request.get("chat_id")
    is_group = request.get("is_group", False)
    username = request.get("username")
    
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    
    # Запускаем периодические задачи
    background_tasks.add_task(auto_reload_core, background_tasks)
    
    # Обрабатываем сообщение
    response = await process_message(message, chat_id, is_group, username)
    
    # Проверяем формат ответа
    if isinstance(response, list):
        return {"response_parts": response, "multi_part": True}
    else:
        return {"response": response, "multi_part": False}

@app.post("/webhook")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Обрабатывает вебхуки от Telegram или других источников.
    
    Args:
        request: Объект запроса
        background_tasks: Объект для добавления фоновых задач
        
    Returns:
        Dict[str, Any]: Ответ для обработки вебхуком
    """
    try:
        # Получаем данные из запроса
        data = await request.json()
        print(f"Received webhook data")
        
        # Проверяем, это ли Telegram
        if "message" in data and "text" in data["message"]:
            # Извлекаем данные из сообщения Telegram
            message = data["message"]["text"]
            chat_id = str(data["message"]["chat"]["id"])
            is_group = data["message"]["chat"]["type"] in ["group", "supergroup"]
            username = data["message"].get("from", {}).get("username")
            
            # Запускаем периодические задачи
            background_tasks.add_task(auto_reload_core, background_tasks)
            
            # Обрабатываем сообщение
            response = await process_message(message, chat_id, is_group, username)
            
            # Возвращаем ответ для дальнейшей обработки через API Telegram
            if isinstance(response, list):
                return {"response_parts": response, "chat_id": chat_id, "multi_part": True}
            else:
                return {"response": response, "chat_id": chat_id, "multi_part": False}
        
        # Для других источников
        return {"status": "received"}
    except Exception as e:
        print(f"Error handling webhook: {e}")
        log_event({"type": "webhook_error", "error": str(e)})
        return {"status": "error", "error": str(e)}

@app.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)]
) -> Dict[str, Any]:
    """
    Загружает файл и сохраняет его на сервере.
    
    Args:
        background_tasks: Объект для добавления фоновых задач
        file: Загруженный файл
        
    Returns:
        Dict[str, Any]: Информация о загруженном файле
    """
    try:
        # Создаем имя файла с временной меткой
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{file.filename.replace(' ', '_')}"
        file_path = os.path.join(UPLOADS_DIR, safe_filename)
        
        # Сохраняем файл
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Запускаем периодические задачи
        background_tasks.add_task(auto_reload_core, background_tasks)
        
        log_event({"type": "file_uploaded", "filename": safe_filename, "size": len(contents)})
        
        return {
            "filename": safe_filename,
            "path": file_path,
            "size": len(contents),
            "content_type": file.content_type
        }
    except Exception as e:
        print(f"Error uploading file: {e}")
        log_event({"type": "file_upload_error", "error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/file")
async def handle_file(
    background_tasks: BackgroundTasks,
    request: Annotated[Dict[str, Any], Body(...)]
) -> Dict[str, Any]:
    """
    Обрабатывает загруженные файлы.
    
    Args:
        background_tasks: Объект для добавления фоновых задач
        request: Тело запроса с путем к файлу
        
    Returns:
        Dict[str, Any]: Извлеченный текст из файла
    """
    file_path = request.get("file_path", "")
    
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail="Valid file_path is required")
    
    # Запускаем периодические задачи
    background_tasks.add_task(auto_reload_core, background_tasks)
    
    # Обрабатываем файл
    content = await process_file(file_path)
    
    # Разбиваем контент на части, если он слишком длинный
    content_parts = process_text(content, MAX_RESPONSE_LENGTH) if len(content) > MAX_RESPONSE_LENGTH else [content]
    
    if len(content_parts) > 1:
        return {"content_parts": content_parts, "multi_part": True}
    else:
        return {"content": content_parts[0], "multi_part": False}

@app.get("/healthz")
async def healthcheck() -> Dict[str, str]:
    """
    Проверка работоспособности для мониторинга.
    
    Returns:
        Dict[str, str]: Статус здоровья системы
    """
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/status")
async def status() -> Dict[str, Any]:
    """
    Расширенный статус приложения.
    
    Returns:
        Dict[str, Any]: Детальный статус системы
    """
    global core_config, last_check, last_wilderness
    
    # Проверяем доступность векторного хранилища
    vector_store_status = "checking..."
    try:
        vector_store_status = "available" if await is_vector_store_available() else "unavailable"
    except:
        vector_store_status = "error"
    
    return {
        "status": "operational",
        "name": AGENT_NAME,
        "version": VERSION,
        "last_core_check": datetime.fromtimestamp(last_check).isoformat(),
        "last_wilderness": datetime.fromtimestamp(last_wilderness).isoformat(),
        "next_wilderness": (datetime.fromtimestamp(last_wilderness) + 
                           timedelta(hours=WILDERNESS_INTERVAL)).isoformat(),
        "config_version": core_config.get("version") if core_config else "unknown",
        "memory_chats": len(memory_cache),
        "vector_store": vector_store_status,
        "openai_api": "configured" if OPENAI_API_KEY else "not configured"
    }

@app.get("/wilderness")
async def trigger_wilderness(
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Ручной запуск wilderness excursion.
    
    Args:
        background_tasks: Объект для добавления фоновых задач
        
    Returns:
        Dict[str, Any]: Результат wilderness excursion
    """
    global last_wilderness
    
    # Запускаем wilderness excursion
    reflection = await wilderness_excursion()
    last_wilderness = time.time()
    
    # Запускаем периодические задачи
    background_tasks.add_task(auto_reload_core, background_tasks)
    
    if reflection:
        return {
            "status": "success", 
            "reflection": reflection, 
            "next_scheduled": (datetime.fromtimestamp(last_wilderness) + 
                              timedelta(hours=WILDERNESS_INTERVAL)).isoformat()
        }
    else:
        return {"status": "error", "message": "Failed to generate wilderness reflection"}

# Точка входа для запуска сервера
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=True)
