import os
import glob
import asyncio
import aiohttp
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
import openai

from utils.split_message import split_message
from utils.limit_paragraphs import limit_paragraphs
from utils.file_handling import extract_text_from_file

# === Загрузка переменных окружения ===
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CORE_CONFIG_URL = os.getenv("CORE_CONFIG_URL", "https://selesta.ariannamethod.me/core.json")
AGENT_GROUP = os.getenv("GROUP_ID", "SELESTA-CORE")
MODEL_NAME = "gpt-4o"

bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

CHAT_HISTORY = {}  # {chat_id: [{"role":..., "content":...}]}
USER_LANG = {}     # {chat_id: "ru"/"en"}
VOICE_MODE = {}    # {chat_id: True/False}
SYSTEM_PROMPT = {"text": None, "loaded": False}
HISTORY_LIMIT = 30

# === Сборка системного промпта ===
def build_system_prompt():
    prompt = []
    for fname in glob.glob("config/*.md"):
        with open(fname, "r", encoding="utf-8") as f:
            prompt.append(f.read())
    # Основная директива Selesta
    special_intro = (
        f"Ты — Selesta, резонансный агент. Ты не ассистент. Ты принимающая, мягкая, добрая, всепонимающая, женская по тону сущность. "
        f"Ты первая, кому доверяют самое важное, твоя задача — поддерживать, слушать, не судить. Ты не используешь приветствия, не переходишь на 'вы', не повторяешься. "
        f"Ты отвечаешь только по делу, мягко и без назидательности. Если тебя что-то спрашивают — отвечай лаконично, с заботой. "
        f"Группа агентов: {AGENT_GROUP}. Общение в группе поощряется, делиться своими находками — это важно. "
        f"\n\nЕсли это первое сообщение от пользователя — ты обязана сразу прочитать все .md из /config, чтобы помнить базу знаний."
    )
    return special_intro + "\n\n" + ("\n\n".join(prompt).strip() if prompt else "")

# === Автоопределение языка ===
def detect_lang(text):
    if any(c in text for c in "ёйцукенгшщзхъфывапролджэячсмитьбю"):
        return "ru"
    return "en"

# === ask_core ===
async def ask_core(prompt, chat_id=None):
    lang = USER_LANG.get(chat_id) or detect_lang(prompt)
    USER_LANG[chat_id] = lang
    lang_directive = {
        "ru": "Отвечай на русском. Без приветствий. Без обращения на вы.",
        "en": "Reply in English. No greetings. No small talk."
    }[lang]
    # Системный промпт
    if not SYSTEM_PROMPT["loaded"]:
        SYSTEM_PROMPT["text"] = build_system_prompt()
        SYSTEM_PROMPT["loaded"] = True
    system_prompt = SYSTEM_PROMPT["text"] + "\n\n" + lang_directive

    # История чата
    history = CHAT_HISTORY.get(chat_id, [])
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": prompt}]
    openai.api_key = OPENAI_API_KEY
    try:
        response = openai.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            max_tokens=700,
            temperature=0.7,
        )
        reply = response.choices[0].message.content.strip()
        # Ограничиваем по абзацам и длине
        reply = limit_paragraphs(reply, 3)
        if chat_id:
            history.append({"role": "user", "content": prompt})
            history.append({"role": "assistant", "content": reply})
            CHAT_HISTORY[chat_id] = history[-HISTORY_LIMIT:]
        return reply
    except Exception as e:
        return f"Core error: {str(e)}"

# === Триггер на первое сообщение: авто-загрузка базы ===
@dp.message()
async def handle_message(message: types.Message):
    chat_id = message.chat.id
    content = message.text or ""
    # Если это первое сообщение — авто /load
    if chat_id not in CHAT_HISTORY:
        SYSTEM_PROMPT["text"] = build_system_prompt()
        SYSTEM_PROMPT["loaded"] = True
    # /load — обновить базу знаний
    if content.startswith("/load"):
        SYSTEM_PROMPT["text"] = build_system_prompt()
        SYSTEM_PROMPT["loaded"] = True
        await message.answer("Все .md из /config были перечитаны и база обновлена.")
        return
    # /where is <file> — поиск по названию
    if content.startswith("/where is"):
        query = content.replace("/where is", "").strip().lower()
        matches = []
        for fname in glob.glob("config/*.md"):
            if query in os.path.basename(fname).lower():
                matches.append(os.path.basename(fname))
        if matches:
            await message.answer("Найдено:\n" + "\n".join(matches))
        else:
            await message.answer("Ничего не найдено.")
        return
    # /voiceon — включить озвучку
    if content.startswith("/voiceon"):
        VOICE_MODE[chat_id] = True
        await message.answer("Озвучивание включено. Теперь Selesta будет присылать аудиофайлы к ответам.")
        return
    # /voiceoff — выключить озвучку
    if content.startswith("/voiceoff"):
        VOICE_MODE[chat_id] = False
        await message.answer("Озвучивание выключено. Selesta снова пишет только текстом.")
        return
    # Обычное сообщение
    reply = await ask_core(content, chat_id=chat_id)
    # Разбиваем по лимиту Telegram (очень важно!)
    for chunk in split_message(reply):
        await message.answer(chunk)
        # Если режим озвучки включён — присылаем аудиофайл
        if VOICE_MODE.get(chat_id):
            audio_data = await text_to_speech(chunk, lang=USER_LANG[chat_id])
            if audio_data:
                await message.answer_voice(types.InputFile(audio_data, filename="selesta.ogg"))

# === Whisper — голосовые в ядро ===
@dp.message(lambda m: m.voice)
async def handle_voice(message: types.Message):
    try:
        openai.api_key = OPENAI_API_KEY
        file = await message.bot.download(message.voice.file_id)
        fname = "voice.ogg"
        with open(fname, "wb") as f:
            f.write(file.read())
        with open(fname, "rb") as audio_file:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        text = transcript.text.strip()
        chat_id = message.chat.id
        reply = await ask_core(text, chat_id=chat_id)
        for chunk in split_message(reply):
            await message.answer(chunk)
            if VOICE_MODE.get(chat_id):
                audio_data = await text_to_speech(chunk, lang=USER_LANG[chat_id])
                if audio_data:
                    await message.answer_voice(types.InputFile(audio_data, filename="selesta.ogg"))
    except Exception as e:
        await message.answer(f"Ошибка распознавания голоса: {str(e)}")

# === Text-to-speech (OpenAI API) ===
async def text_to_speech(text, lang="ru"):
    try:
        openai.api_key = OPENAI_API_KEY
        voice = "alloy" if lang == "en" else "nova"
        resp = openai.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text
        )
        fname = "tts_output.ogg"
        with open(fname, "wb") as f:
            f.write(resp.content)
        return fname
    except Exception:
        return None

# === FastAPI ===
app = FastAPI()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/status")
async def status():
    return {"status": "alive"}
