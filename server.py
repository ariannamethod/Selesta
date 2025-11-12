import os
import json
import asyncio
import time
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union

from pydantic import BaseModel

# FastAPI для API-сервера
from fastapi import FastAPI, Request, Body, BackgroundTasks, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Импортируем утилиты
from utils.claude import claude_emergency
from utils.file_handling import extract_text_from_file_async
from utils.imagine import generate_image_async
from utils.journal import log_event, wilderness_log
from utils.lighthouse import check_core_json
from utils.resonator import build_system_prompt, get_random_wilderness_topic
from utils.text_helpers import extract_text_from_url_async, summarize_text
from utils.text_processing import process_text, send_long_message
from utils.vector_store import vectorize_all_files, semantic_search, is_vector_store_available
from utils.telegram_sender import (
    send_message,
    send_multipart_message,
    send_typing,
    send_audio_message,
)
from utils.voice import download_telegram_file, transcribe_audio, text_to_speech
from langdetect import detect, LangDetectException

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
MAX_RESPONSE_LENGTH = 4096  # Максимальная длина одного сообщения (технический лимит Telegram)
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))  # 10 MB

# Имя бота и дополнительные параметры для группового поведения
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lower()
NAME_ALIASES = ["селеста", "selesta", "celesta"]
GROUP_DELAY_RANGE = (40, 240)  # Задержка ответов в группах (секунды)

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
# Режим голосовых ответов для чатов
voice_mode: Dict[str, bool] = {}
# Флаг для предотвращения повторной векторизации при множественных стартах
vectorization_done = False
# Персистентный файл-замок, чтобы векторизация выполнялась только однажды
VECTOR_LOCK_FILE = os.path.join(DATA_DIR, "vectorization.lock")
# Минимальное время между повторными векторизациями (24 часа)
VECTOR_LOCK_TTL = 24 * 3600


class MessageRequest(BaseModel):
    message: str
    chat_id: str
    is_group: bool = False
    username: Optional[str] = None
    reply_to_bot: bool = False


class MessageResponse(BaseModel):
    response: Optional[str] = None
    response_parts: Optional[List[str]] = None
    multi_part: bool

async def startup_vectorization() -> None:
    """Проверяет и обновляет векторное хранилище после запуска.

    Защита от повторного запуска нужна, поскольку в некоторых окружениях
    событие старта может происходить несколько раз (например, при
    перезапуске воркеров). Флаг ``vectorization_done`` гарантирует, что
    векторизация выполняется только один раз за процесс.
    """
    global vectorization_done

    if vectorization_done or not OPENAI_API_KEY:
        return

    if os.path.exists(VECTOR_LOCK_FILE):
        try:
            with open(VECTOR_LOCK_FILE, "r") as _lock:
                ts = _lock.read().strip()
            last_time = datetime.fromisoformat(ts)
            if (datetime.utcnow() - last_time).total_seconds() < VECTOR_LOCK_TTL:
                print("Vectorization recently performed, skipping.")
                vectorization_done = True
                return
        except Exception:
            # При ошибке чтения файла просто продолжаем
            pass
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

async def initialize_config() -> MessageResponse:
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

def should_reply_in_group(
    message: str,
    reply_to_bot: bool = False,
    *,
    username: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """Determines whether Selesta should reply in a group chat."""
    text = message.lower()
    if reply_to_bot:
        return True
    if chat_id and CREATOR_CHAT_ID and chat_id == CREATOR_CHAT_ID:
        return True
    if username and CREATOR_USERNAME and username.lower() == CREATOR_USERNAME.lower():
        return True
    if any(alias in text for alias in NAME_ALIASES):
        return True
    if BOT_USERNAME and f"@{BOT_USERNAME}" in text:
        return True
    if any(t in text for t in TRIGGER_WORDS):
        return True
    return False

async def process_message(
    message: str,
    chat_id: Optional[str] = None,
    is_group: bool = False,
    username: Optional[str] = None,
    reply_to_bot: bool = False,
) -> Union[str, List[str], None]:
    """
    Основная функция обработки сообщений от пользователя.
    Возвращает ответ Селесты.
    
    Args:
        message: Текст сообщения
        chat_id: ID чата
        is_group: Является ли чат групповым
        username: Имя пользователя
        
    Returns:
        Union[str, List[str], None]: Ответ Селесты или ``None`` если ответа нет
    """
    try:
        # Voice mode commands
        if chat_id and message.strip().lower() == "/voiceon":
            voice_mode[chat_id] = True
            return "📢"  # Megaphone emoji indicates voice mode is on
        if chat_id and message.strip().lower() == "/voiceoff":
            voice_mode[chat_id] = False
            return "🔇"  # Muted speaker emoji indicates voice mode is off

        # В группах отвечаем только при наличии триггеров или для приоритетных собеседников
        if is_group and not should_reply_in_group(
            message,
            reply_to_bot,
            username=username,
            chat_id=chat_id,
        ):
            return None

        language = None
        try:
            lang_code = detect(message) if message.strip() else ""
            LANG_MAP = {
                "ru": "Russian",
                "en": "English",
                "uk": "Ukrainian",
                "de": "German",
                "fr": "French",
                "es": "Spanish",
            }
            language = LANG_MAP.get(lang_code, "English")
        except LangDetectException:
            language = None

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
            image_url = await generate_image_async(prompt, chat_id)
            return f"🎨 {image_url}"
        
        # Проверка на URL в сообщении
        if "http://" in message or "https://" in message:
            # Извлекаем URL из сообщения
            words = message.split()
            urls = [w for w in words if w.startswith("http://") or w.startswith("https://")]
            if urls:
                url = urls[0]
                try:
                    # Извлекаем текст со страницы
                    text = await extract_text_from_url_async(url)
                    # Суммаризируем текст для удобочитаемости
                    text = summarize_text(text, 1500)
                    # Добавляем контекст URL к исходному сообщению
                    message += f"\n\nContext from {url}:\n{text}"
                except Exception as e:
                    message += f"\n\n[Failed to retrieve context from {url}: {e}]"
        
        # Создаем системный промпт с учетом контекста сообщения
        system_prompt = build_system_prompt(
            chat_id=chat_id,
            is_group=is_group,
            message_context=message,
            language=language,
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
    
    # Wilderness completed, further checks will be triggered by other requests

# Periodic background loop for configuration and wilderness checks
check_task_started = False

async def periodic_checks_loop() -> None:
    """Runs core and wilderness checks periodically without duplicating tasks."""
    global check_task_started
    if check_task_started:
        return
    check_task_started = True
    while True:
        background = BackgroundTasks()
        await auto_reload_core(background)
        await asyncio.sleep(CHECK_INTERVAL)

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
    asyncio.create_task(periodic_checks_loop())

@app.get("/")
async def root():
    """Корневой маршрут с основной информацией."""
    return {
        "name": AGENT_NAME,
        "version": VERSION,
        "status": "operational",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/message", response_model=MessageResponse)
async def handle_message(
    background_tasks: BackgroundTasks,
    request: MessageRequest
) -> MessageResponse:
    """
    Обрабатывает входящие текстовые сообщения.
    
    Args:
        background_tasks: Объект для добавления фоновых задач
        request: Данные сообщения и метаданные
        
    Returns:
        MessageResponse: Ответ с сообщением Селесты
    """
    message = request.message
    chat_id = request.chat_id
    is_group = request.is_group
    username = request.username
    reply_to_bot = request.reply_to_bot
    
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    
    
    # Обрабатываем сообщение
    response = await process_message(
        message,
        chat_id,
        is_group,
        username,
        reply_to_bot=reply_to_bot,
    )
    
    # Проверяем формат ответа
    if response is None:
        return MessageResponse(response=None, multi_part=False)
    elif isinstance(response, list):
        return MessageResponse(response_parts=response, multi_part=True)
    else:
        return MessageResponse(response=response, multi_part=False)

async def process_and_send_response(
    message: str,
    chat_id: str,
    is_group: bool,
    username: Optional[str],
    reply_to_bot: bool = False,
    reply_to_message_id: Optional[int] = None,
) -> None:
    """Process a message and send the response via Telegram asynchronously."""
    try:
        if is_group and not should_reply_in_group(
            message,
            reply_to_bot,
            username=username,
            chat_id=chat_id,
        ):
            return

        if is_group:
            await asyncio.sleep(
                GROUP_DELAY_RANGE[0]
                if GROUP_DELAY_RANGE[0] == GROUP_DELAY_RANGE[1]
                else random.uniform(*GROUP_DELAY_RANGE)
            )

        await send_typing(chat_id)
        response = await process_message(
            message,
            chat_id,
            is_group,
            username,
            reply_to_bot=reply_to_bot,
        )

        if response is None:
            return

        if voice_mode.get(chat_id) and message.strip().lower() not in ["/voiceon", "/voiceoff"]:
            text_resp = response if not isinstance(response, list) else "\n\n".join(response)
            voice_file = os.path.join(UPLOADS_DIR, f"reply_{int(time.time())}.mp3")
            await text_to_speech(text_resp, voice_file)
            sent = await send_audio_message(
                chat_id,
                voice_file,
                caption=text_resp,
                reply_to_message_id=reply_to_message_id,
            )
            try:
                os.remove(voice_file)
            except Exception:
                pass
        else:
            if isinstance(response, list):
                sent = await send_multipart_message(chat_id, response, reply_to_message_id=reply_to_message_id)
            else:
                sent = await send_message(chat_id, response, reply_to_message_id)

        if not sent:
            log_event({"type": "send_error", "chat_id": chat_id, "message": "delivery failed"})
    except Exception as e:
        print(f"Error in process_and_send_response: {e}")
        log_event({"type": "send_error", "error": str(e), "chat_id": chat_id})

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
        print("Received webhook data")
        
        # Проверяем, это ли Telegram
        if "message" in data:
            chat = data["message"].get("chat", {})
            chat_id = str(chat.get("id"))
            is_group = chat.get("type") in ["group", "supergroup"]
            username = data["message"].get("from", {}).get("username")
            message_id = data["message"].get("message_id")
            if "text" in data["message"]:
                message = data["message"]["text"]
            elif "voice" in data["message"]:
                file_id = data["message"]["voice"]["file_id"]
                temp_path = os.path.join(UPLOADS_DIR, f"{file_id}.ogg")
                downloaded = await download_telegram_file(file_id, temp_path)
                message = await transcribe_audio(downloaded) if downloaded else ""
            else:
                message = ""
            
            # Обрабатываем сообщение в фоне и сразу отвечаем webhook
            reply_to_bot = False
            if "reply_to_message" in data["message"]:
                orig = data["message"]["reply_to_message"].get("from", {})
                if orig.get("is_bot") and (not BOT_USERNAME or orig.get("username", "").lower() == BOT_USERNAME):
                    reply_to_bot = True

            background_tasks.add_task(
                process_and_send_response,
                message,
                chat_id,
                is_group,
                username,
                reply_to_bot,
                message_id,
            )
            return {"status": "accepted", "chat_id": chat_id}
        
        # Для других источников
        return {"status": "received"}
    except Exception as e:
        print(f"Error handling webhook: {e}")
        log_event({"type": "webhook_error", "error": str(e)})
        return {"status": "error", "error": str(e)}

@app.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
) -> Dict[str, str]:
    f"""
    Загружает файл и сохраняет его на сервере.

    Максимальный размер файла: {MAX_UPLOAD_SIZE // (1024 * 1024)} MB.

    Args:
        background_tasks: Объект для добавления фоновых задач
        file: Загруженный файл

    Returns:
        Dict[str, str]: Информация о загруженном файле
    """
    chunk_size = 1024 * 1024  # 1 MB
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename.replace(' ', '_')}"
    file_path = os.path.join(UPLOADS_DIR, safe_filename)

    try:
        content_length = file.headers.get("content-length")
        if content_length and int(content_length) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large")

        total_size = 0
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="File too large")
                f.write(chunk)

        log_event({"type": "file_uploaded", "filename": safe_filename, "size": total_size})

        return {
            "filename": safe_filename,
            "path": file_path,
            "size": total_size,
            "content_type": file.content_type
        }
    except HTTPException:
        if os.path.exists(file_path):
            os.remove(file_path)
        log_event({"type": "file_upload_error", "error": "File too large"})
        raise
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        print(f"Error uploading file: {e}")
        log_event({"type": "file_upload_error", "error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/file")
async def handle_file(
    background_tasks: BackgroundTasks,
    request: Dict[str, Any] = Body(...)
) -> Dict[str, str]:
    """
    Обрабатывает загруженные файлы.
    
    Args:
        background_tasks: Объект для добавления фоновых задач
        request: Тело запроса с путем к файлу
        
    Returns:
        Dict[str, str]: Извлеченный текст из файла
    """
    file_path = request.get("file_path", "")
    
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail="Valid file_path is required")
    
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
async def status() -> MessageResponse:
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
    except Exception:
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
) -> MessageResponse:
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
