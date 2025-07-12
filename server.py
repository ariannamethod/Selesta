import os
import json
import asyncio
import random
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# FastAPI для API-сервера
from fastapi import FastAPI, Request, Body, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Импортируем утилиты
from utils.claude import claude_emergency
from utils.file_handling import extract_text_from_file_async
from utils.imagine import generate_image
from utils.journal import log_event, wilderness_log
from utils.lighthouse import check_core_json
from utils.limit_paragraphs import limit_paragraphs
from utils.resonator import build_system_prompt, WILDERNESS_TOPICS
from utils.split_message import split_message
from utils.text_helpers import extract_text_from_url, fuzzy_match
from utils.vector_store import vectorize_all_files, semantic_search

# Получаем ключи API из переменных окружения
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CREATOR_CHAT_ID = os.getenv("CREATOR_CHAT_ID")

# Константы
AGENT_NAME = "Selesta"
VERSION = "1.0.0"
CHECK_INTERVAL = 3600  # Проверка конфигурации каждый час
WILDERNESS_INTERVAL = 72  # Wilderness excursion каждые 72 часа
TRIGGER_WORDS = ["нарисуй", "представь", "визуализируй", "изобрази", "draw", "imagine", "visualize"]

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

# Глобальные переменные
core_config = None
last_check = 0
last_wilderness = 0

async def initialize_config():
    """Загружает и инициализирует конфигурацию Селесты."""
    try:
        # Проверка core.json через "маяк"
        core_config = await check_core_json()
        if not core_config:
            print("Failed to load core config, using local config.")
            with open("config/core.json", "r", encoding="utf-8") as f:
                core_config = json.load(f)
        
        # Векторизация конфигурационных файлов для семантического поиска
        if OPENAI_API_KEY:
            print("Vectorizing config files...")
            await vectorize_all_files(
                openai_api_key=OPENAI_API_KEY,
                force=False,
                on_message=lambda msg: print(f"Vectorization: {msg}")
            )
        else:
            print("Warning: OpenAI API key not set, skipping vectorization.")
        
        print(f"{AGENT_NAME} v{VERSION} initialized successfully.")
        log_event({"type": "init", "status": "success", "version": VERSION})
        return core_config
    except Exception as e:
        print(f"Error during initialization: {e}")
        log_event({"type": "init", "status": "error", "error": str(e)})
        return None

async def wilderness_excursion():
    """
    Периодическая функция для 'экскурсий в wilderness' - 
    генерации творческих размышлений на философские темы.
    """
    try:
        # Выбираем случайную тему
        topic = random.choice(WILDERNESS_TOPICS)
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

async def process_message(message: str, chat_id: Optional[str] = None, 
                         is_group: bool = False, username: Optional[str] = None) -> str:
    """
    Основная функция обработки сообщений от пользователя.
    Возвращает ответ Селесты.
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
                # Ограничиваем количество параграфов для читаемости
                text = limit_paragraphs(text)
                # Добавляем контекст URL к исходному сообщению
                message += f"\n\nContext from {url}:\n{text}"
        
        # Создаем системный промпт
        system_prompt = build_system_prompt(chat_id=chat_id, is_group=is_group)
        
        # Определяем контекст из конфигурационных файлов через семантический поиск
        if OPENAI_API_KEY:
            context_chunks = await semantic_search(message, OPENAI_API_KEY, top_k=3)
            context = "\n\n".join(context_chunks)
        else:
            context = ""
        
        # Формируем финальный промпт для модели с контекстом
        full_prompt = f"{message}\n\n"
        if context:
            full_prompt += f"--- Context from Configuration ---\n{context}\n\n"
            
        # В реальном приложении здесь был бы вызов к OpenAI или другой модели
        # Для примера используем Claude как аварийный фоллбек
        response = await claude_emergency(
            full_prompt, 
            notify_creator=chat_id==CREATOR_CHAT_ID
        )
        
        # Логируем взаимодействие
        log_event({
            "type": "interaction",
            "chat_id": chat_id,
            "username": username,
            "is_group": is_group,
            "length": len(message)
        })
        
        return response
    except Exception as e:
        print(f"Error processing message: {e}")
        log_event({"type": "error", "error": str(e)})
        return "💎"  # Тихий символ ошибки

async def process_file(file_path: str) -> str:
    """Обрабатывает загруженный файл и возвращает его содержимое."""
    try:
        text = await extract_text_from_file_async(file_path)
        log_event({"type": "file_processed", "path": file_path})
        return text
    except Exception as e:
        print(f"Error processing file: {e}")
        log_event({"type": "error", "error": str(e)})
        return f"[Error processing file: {e}]"

# Периодические задачи
async def auto_reload_core(background_tasks: BackgroundTasks):
    """Периодически проверяет обновления конфигурации."""
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

async def check_wilderness(background_tasks: BackgroundTasks):
    """Периодически запускает wilderness excursion."""
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
    
    print("Starting Selesta Assistant...")
    core_config = await initialize_config()
    last_check = time.time()
    last_wilderness = time.time()

@app.get("/")
async def root():
    """Корневой маршрут с основной информацией."""
    return {
        "name": AGENT_NAME,
        "version": VERSION,
        "status": "operational"
    }

@app.post("/message")
async def handle_message(
    background_tasks: BackgroundTasks,
    request: Dict[str, Any] = Body(...)
):
    """Обрабатывает входящие текстовые сообщения."""
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
    
    return {"response": response}

@app.post("/file")
async def handle_file(
    background_tasks: BackgroundTasks,
    request: Dict[str, Any] = Body(...)
):
    """Обрабатывает загруженные файлы."""
    file_path = request.get("file_path", "")
    
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail="Valid file_path is required")
    
    # Запускаем периодические задачи
    background_tasks.add_task(auto_reload_core, background_tasks)
    
    # Обрабатываем файл
    content = await process_file(file_path)
    
    return {"content": content}

@app.get("/healthz")
async def healthcheck():
    """Проверка работоспособности для мониторинга."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/status")
async def status():
    """Расширенный статус приложения."""
    global core_config, last_check, last_wilderness
    
    return {
        "status": "operational",
        "version": VERSION,
        "last_core_check": datetime.fromtimestamp(last_check).isoformat(),
        "last_wilderness": datetime.fromtimestamp(last_wilderness).isoformat(),
        "next_wilderness": (datetime.fromtimestamp(last_wilderness) + 
                           timedelta(hours=WILDERNESS_INTERVAL)).isoformat(),
        "config_version": core_config.get("version") if core_config else "unknown"
    }

# Точка входа для запуска сервера
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
