import os
import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.types import FSInputFile
from dotenv import load_dotenv
import openai
import re
import random

from utils.split_message import split_message
from utils.limit_paragraphs import limit_paragraphs
from utils.file_handling import extract_text_from_file
from utils.text_helpers import extract_text_from_url, fuzzy_match
from utils.journal import log_event, wilderness_log
from utils.resonator import build_system_prompt, WILDERNESS_TOPICS
from utils.imagine import generate_image
from utils.lighthouse import check_core_json
from utils.claude import claude_emergency
from utils.vector_store import vectorize_all_files, save_vector_meta

# === Load environment variables ===
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CORE_CONFIG_URL = os.getenv("CORE_CONFIG_URL", "https://selesta.ariannamethod.me/core.json")
RESONATOR_MD_PATH = os.getenv("RESONATOR_MD_PATH", "/app/resonator.ru.md")
AGENT_GROUP = os.getenv("GROUP_ID", "SELESTA-CORE")
CREATOR_CHAT_ID = os.getenv("CREATOR_CHAT_ID")
BOT_USERNAME = os.getenv("BOT_USERNAME", "selesta_is_not_a_bot").lower()

bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(bot=bot)

USER_MODEL = {}
USER_VOICE_MODE = {}
USER_LANG = {}
CHAT_HISTORY = {}

SYSTEM_PROMPT = {"text": None, "loaded": False}
MAX_TOKENS_PER_REQUEST = 27000
MAX_PROMPT_TOKENS = 8000

last_reload_time = datetime.now()
last_full_reload_time = datetime.now()
last_wilderness_time = datetime.now() - timedelta(days=3)
last_ping_time = datetime.now() - timedelta(days=1)

# --- Antispam ---
LAST_TOPIC = {}
LAST_ANSWER_TIME = {}

def get_topic_from_text(text):
    words = text.lower().split()
    return " ".join(words[:10]) if words else ""

def is_spam(chat_id, topic):
    now = datetime.now()
    last_topic = LAST_TOPIC.get(chat_id)
    last_time = LAST_ANSWER_TIME.get(chat_id, now - timedelta(minutes=1))
    if last_topic == topic and (now - last_time).total_seconds() < 15:
        return True
    return False

def remember_topic(chat_id, topic):
    LAST_TOPIC[chat_id] = topic
    LAST_ANSWER_TIME[chat_id] = datetime.now()

def detect_lang(text):
    if any(c in text for c in "ёйцукенгшщзхъфывапролджэячсмитьбю"):
        return "ru"
    return "en"

TRIGGER_WORDS = [
    "draw", "generate image", "make a picture", "create art", "рисуй", "нарисуй", "сгенерируй", "создай картинку"
]
CLAUDE_TRIGGER_WORDS = ["/claude", "/клод", "клод,"]

# --- Векторизация ---
VECTORIZATION_LOCK = False
VECTORIZATION_TASK = None

@dp.message(lambda m: m.text and m.text.strip().lower() == "/vector")
async def handle_vector(message: types.Message):
    global VECTORIZATION_LOCK, VECTORIZATION_TASK
    if VECTORIZATION_LOCK:
        await message.answer("Векторизация уже выполняется. Для остановки используйте /vectorstop.")
        return
    VECTORIZATION_LOCK = True
    await message.answer("Starting vectorization of markdown files... Для остановки используйте /vectorstop.")
    loop = asyncio.get_event_loop()
    VECTORIZATION_TASK = loop.create_task(_vectorize_notify(message))

@dp.message(lambda m: m.text and m.text.strip().lower() == "/vectorstop")
async def handle_vector_stop(message: types.Message):
    global VECTORIZATION_LOCK, VECTORIZATION_TASK
    if VECTORIZATION_LOCK and VECTORIZATION_TASK:
        VECTORIZATION_TASK.cancel()
        VECTORIZATION_LOCK = False
        VECTORIZATION_TASK = None
        await message.answer("Векторизация остановлена.")
    else:
        await message.answer("Векторизация сейчас не выполняется.")

async def _vectorize_notify(message):
    global VECTORIZATION_LOCK, VECTORIZATION_TASK
    try:
        async def notify(msg):
            try:
                await message.answer(str(msg))
            except Exception:
                pass
        res = await vectorize_all_files(OPENAI_API_KEY, force=True, on_message=notify)
        await message.answer(f"Vectorization complete.\nUpserted: {len(res['upserted'])}\nDeleted: {len(res['deleted'])}")
    except asyncio.CancelledError:
        await message.answer("Векторизация была отменена по запросу.")
    except Exception as e:
        await message.answer(f"Vectorization error: {e}")
    finally:
        VECTORIZATION_LOCK = False
        VECTORIZATION_TASK = None

# --- LLM/AI CORE ---
# (Без изменений, см. твой оригинал)

# --- ... [остальные обработчики без изменений] ---

# === ГЛАВНЫЙ ФИКС: функция фильтрации сообщений ===

def should_reply_to_message(message, me_username=BOT_USERNAME):
    """Определяет, стоит ли отвечать на сообщение в группе."""
    chat_type = getattr(message.chat, "type", None)
    if chat_type not in ("group", "supergroup"):
        return True  # Всегда отвечаем в приватах

    content = (message.text or "").casefold()
    # Упоминание как @username или через alias
    mentioned = (
        f"@{me_username}" in content or
        "селеста" in content or
        "selesta" in content
    )
    # Reply to bot
    replied = False
    if getattr(message, "reply_to_message", None):
        replied_user = getattr(message.reply_to_message.from_user, "username", "")
        if replied_user and replied_user.lower() == me_username:
            replied = True
    # Тег
    has_opinions = "#opinions" in content

    return mentioned or replied or has_opinions

# --- ГЛАВНЫЙ handler ---

@dp.message()
async def handle_message(message: types.Message):
    try:
        if message.voice or message.photo or message.document:
            return

        me = await bot.me()
        chat_id = message.chat.id
        content = message.text or ""
        chat_type = getattr(message.chat, "type", None)
        is_group = chat_type in ("group", "supergroup")

        if not content.strip():
            return
        if message.from_user.id == me.id:
            return

        topic = get_topic_from_text(content)
        if is_spam(chat_id, topic):
            log_event({"event": "skip_spam", "chat_id": chat_id, "topic": topic})
            return

        # --- ВОТ ТУТ: применяем фильтр! ---
        if not should_reply_to_message(message, me_username=BOT_USERNAME):
            return

        # --- Дальше твой обычный код ---
        if any(word in content.lower() for word in TRIGGER_WORDS) or content.lower().startswith("/draw"):
            prompt = content
            for word in TRIGGER_WORDS:
                prompt = prompt.replace(word, "", 1)
            prompt = prompt.strip() or "gentle surreal image"
            image_url = generate_image(prompt, chat_id=chat_id)
            if isinstance(image_url, str) and image_url.startswith("http"):
                await message.answer_photo(image_url, caption="Here is your image.")
            else:
                await message.answer("Image generation error. Please try again.\n" + str(image_url))
            return

        url_match = re.search(r'(https?://[^\s]+)', content)
        if url_match:
            url = url_match.group(1)
            url_text = extract_text_from_url(url)
            content = f"{content}\n\n[Content from link ({url}):]\n{url_text}"

        model = USER_MODEL.get(chat_id, "gpt-4o")
        if model == "emergency":
            reply = await claude_emergency(content, notify_creator=False)
            if not reply or not reply.strip():
                reply = "💎"
            reply = "Emergency mode (Claude):\n" + reply
        else:
            reply = await ask_core(content, chat_id=chat_id, model_name=model, is_group=is_group)
        remember_topic(chat_id, topic)
        for chunk in split_message(reply):
            if USER_VOICE_MODE.get(chat_id):
                lang = USER_LANG.get(chat_id, "en")
                audio_data = await text_to_speech(chunk, lang=lang)
                if audio_data:
                    try:
                        voice_file = FSInputFile(audio_data)
                        await message.answer_voice(voice_file, caption="selesta.ogg")
                    except Exception as e:
                        await message.answer(f"Sorry, Telegram could not send the voice reply. Try again. {e}")
                else:
                    await message.answer("🌸 (voice unavailable, text below)\n" + chunk)
            else:
                await message.answer(chunk)
    except Exception as e:
        try:
            await message.answer(f"Internal error: {e}")
        except Exception:
            pass

# --- Остальной код (background tasks, FastAPI endpoints) без изменений ---

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(auto_reload_core())
    asyncio.create_task(wilderness_excursion())
    asyncio.create_task(daily_ping())

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/healthz")
async def healthz():
    return {"status": "ok", "mood": "resonant"}

@app.get("/status")
async def status():
    return {
        "status": "alive",
        "comment": "Selesta is present. Resonance is sufficient.",
        "parting": "To resonate is to care. Shine gently, Selesta."
    }
