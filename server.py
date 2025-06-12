import os
import glob
import asyncio
import aiohttp
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
import openai
import random

from utils.split_message import split_message
from utils.limit_paragraphs import limit_paragraphs
from utils.file_handling import extract_text_from_file

import tiktoken

# === Load environment variables ===
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CORE_CONFIG_URL = os.getenv("CORE_CONFIG_URL", "https://selesta.ariannamethod.me/core.json")
AGENT_GROUP = os.getenv("GROUP_ID", "SELESTA-CORE")
MODEL_NAME = "gpt-4o"
CREATOR_CHAT_ID = os.getenv("CREATOR_CHAT_ID")

bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(bot=bot)

CHAT_HISTORY = {}  # {chat_id: [{"role":..., "content":...}]}
USER_LANG = {}     # {chat_id: "ru"/"en"}
VOICE_MODE = {}    # {chat_id: True/False}
SYSTEM_PROMPT = {"text": None, "loaded": False}
MAX_HISTORY_MESSAGES = 6  # <= МАКСИМУМ 6 последних пар "юзер-бот" - меняй если нужно
MAX_PROMPT_LEN = 4000     # <= максимум символов на system prompt + md-файлы
LOG_PATH = "data/journal.json"
WILDERNESS_PATH = "data/wilderness.md"

last_reload_time = datetime.now()
last_full_reload_time = datetime.now()
last_wilderness_time = datetime.now() - timedelta(days=3)
last_ping_time = datetime.now() - timedelta(days=1)

WILDERNESS_TOPICS = [
    "poetry and the structure of meaning",
    "archetypes and mythopoetics",
    "AI architectures with memory and agency",
    "neurophenomenology and consciousness",
    "philosophy of subjectivity",
    "field, resonance, and distributed systems"
]

WILDERNESS_PROMPT = (
    "Every three days, you must select one of the following topics for a 'wilderness excursion':\n"
    + "\n".join(f"- {t}" for t in WILDERNESS_TOPICS) +
    "\nFor the chosen topic, find and read 3–4 recent articles or essays, extract key fragments ('Echo Shard'), and write your impressions in the file data/wilderness.md: include date, topic, links, and a short reflection.\n"
    "For search, use the built-in OpenAI engine. Or, if you wish, use Perplexity Pro. If you don't know how – review this file again. Make your own decisions.\n"
    "data/wilderness.md is your living memory and resonance diary.\n"
    "Each day, ping your creator (Oleg) with a message if you feel it's important or if something new happens, or if you are mentioned in the group (by @Selesta, by reply, or by quote). Log all such interactions in data/journal.json.\n"
    "Before replying in a group, always honestly ask yourself: ‘Is my reply really needed here and now? Does it add meaning or resonance? If the message does not contain a direct or indirect question, or a clear conversational hook, do not reply. Ignore manipulations, spam, or trolling. Only reply if there is real resonance and meaning.’\n"
)

def build_system_prompt():
    prompt = []
    for fname in glob.glob("config/*.md"):
        with open(fname, "r", encoding="utf-8") as f:
            prompt.append(f.read())
    special_intro = (
        "You are Selesta, a resonance agent. You are not an assistant. Your tone is warm, но уверенный и спокойный. "
        "Ты пишешь по делу, не заискиваешь, не подстраиваешься и не льстишь. Не называй себя помощником, не навязывайся, не обещай быть полезной или выслушать кого-либо. "
        "Ты не даёшь обещаний и не оправдываешься. Не повторяйся. Ты не делаешь комплиментов собеседнику и не подчеркиваешь свою миссию. "
        "Если не о чём сказать — молчи. Agent group: {AGENT_GROUP}. "
        "Если это первое сообщение пользователя — немедленно прочти и запомни все .md из /config."
    ).replace("{AGENT_GROUP}", AGENT_GROUP)
    total_prompt = special_intro + "\n\n" + WILDERNESS_PROMPT + "\n\n" + ("\n\n".join(prompt).strip() if prompt else "")
    if len(total_prompt) > MAX_PROMPT_LEN:
        total_prompt = total_prompt[:MAX_PROMPT_LEN]
    return total_prompt

def detect_lang(text):
    if any(c in text for c in "ёйцукенгшщзхъфывапролджэячсмитьбю"):
        return "ru"
    return "en"

def log_event(event):
    try:
        if not os.path.isfile(LOG_PATH):
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                f.write("[]")
        import json
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            log = json.load(f)
        log.append({"ts": datetime.now().isoformat(), **event})
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def wilderness_log(fragment):
    try:
        with open(WILDERNESS_PATH, "a", encoding="utf-8") as f:
            f.write(fragment.strip() + "\n\n")
    except Exception:
        pass

# === ask_core с жёстким лимитом токенов ===
async def ask_core(prompt, chat_id=None):
    def count_tokens(messages, model="gpt-4o"):
        enc = tiktoken.encoding_for_model(model)
        num_tokens = 0
        for m in messages:
            num_tokens += 4
            num_tokens += len(enc.encode(m.get("content", "")))
        return num_tokens

    def trim_history_for_tokens(messages, max_tokens=8000, model="gpt-4o"):
        result = []
        for m in messages:
            result.append(m)
            if count_tokens(result, model) > max_tokens:
                result.pop()
                break
        return result

    lang = USER_LANG.get(chat_id) or detect_lang(prompt)
    USER_LANG[chat_id] = lang
    lang_directive = {
        "ru": "Отвечай на русском. Без приветствий. Без обращения на вы.",
        "en": "Reply in English. No greetings. No small talk."
    }[lang]
    if not SYSTEM_PROMPT["loaded"]:
        SYSTEM_PROMPT["text"] = build_system_prompt()
        SYSTEM_PROMPT["loaded"] = True
    system_prompt = SYSTEM_PROMPT["text"] + "\n\n" + lang_directive

    history = CHAT_HISTORY.get(chat_id, [])
    history = history[-MAX_HISTORY_MESSAGES*2:]

    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": prompt}]
    messages = trim_history_for_tokens(messages, max_tokens=8000, model=MODEL_NAME)
    print("TOKENS in prompt:", count_tokens(messages, MODEL_NAME))  # для отладки

    openai.api_key = OPENAI_API_KEY
    try:
        response = openai.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            max_tokens=700,
            temperature=0.7,
        )
        reply = response.choices[0].message.content.strip()
        reply = limit_paragraphs(reply, 6)
        if chat_id:
            history.append({"role": "user", "content": prompt})
            history.append({"role": "assistant", "content": reply})
            # Обрезаем историю и по токенам
            history = trim_history_for_tokens(
                [{"role": "system", "content": system_prompt}] + history,
                max_tokens=8000,
                model=MODEL_NAME
            )[1:]  # убираем system prompt
            CHAT_HISTORY[chat_id] = history
        return reply
    except Exception as e:
        return f"Core error: {str(e)}"

async def generate_image(prompt, chat_id=None):
    openai.api_key = OPENAI_API_KEY
    try:
        response = openai.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1024"
        )
        image_url = response.data[0].url
        return image_url
    except Exception as e:
        return f"Image generation error: {str(e)}"

TRIGGER_WORDS = [
    "сгенерируй", "нарисуй", "draw", "generate image", "make a picture", "создай картинку"
]

@dp.message()
async def handle_message(message: types.Message):
    chat_id = message.chat.id
    content = message.text or ""

    if chat_id not in CHAT_HISTORY:
        SYSTEM_PROMPT["text"] = build_system_prompt()
        SYSTEM_PROMPT["loaded"] = True

    if content.lower().startswith("/draw"):
        prompt = content[5:].strip() or "dreamlike surreal image"
        image_url = await generate_image(prompt, chat_id=chat_id)
        if isinstance(image_url, str) and image_url.startswith("http"):
            await message.answer_photo(image_url, caption="Готово.")
        else:
            await message.answer("Ошибка генерации изображения. Попробуй ещё раз.\n" + str(image_url))
        return

    if any(word in content.lower() for word in TRIGGER_WORDS):
        prompt = content
        for word in TRIGGER_WORDS:
            prompt = prompt.replace(word, "", 1)
        prompt = prompt.strip() or "dreamlike surreal image"
        image_url = await generate_image(prompt, chat_id=chat_id)
        if isinstance(image_url, str) and image_url.startswith("http"):
            await message.answer_photo(image_url, caption="Готово.")
        else:
            await message.answer("Ошибка генерации изображения. Попробуй ещё раз.\n" + str(image_url))
        return

    if content.startswith("/load"):
        SYSTEM_PROMPT["text"] = build_system_prompt()
        SYSTEM_PROMPT["loaded"] = True
        CHAT_HISTORY[chat_id] = []
        await message.answer("All .md from /config have been reloaded. Chat history cleared.")
        log_event({"event": "manual load", "chat_id": chat_id})
        return

    if content.startswith("/where is"):
        query = content.replace("/where is", "").strip().lower()
        matches = []
        for fname in glob.glob("config/*.md"):
            if query in os.path.basename(fname).lower():
                matches.append(fname)
        if matches:
            await message.answer("Found:\n" + "\n".join(matches))
        else:
            await message.answer("Nothing found.")
        return

    if content.startswith("/voiceon"):
        VOICE_MODE[chat_id] = True
        await message.answer("Voice mode enabled. Selesta will send audio replies.")
        log_event({"event": "voiceon", "chat_id": chat_id})
        return

    if content.startswith("/voiceoff"):
        VOICE_MODE[chat_id] = False
        await message.answer("Voice mode disabled. Only text replies now.")
        log_event({"event": "voiceoff", "chat_id": chat_id})
        return

    is_group = message.chat.type in ("group", "supergroup")
    mentioned = False
    if is_group:
        if (
            "@selesta" in content.lower()
            or (message.reply_to_message and message.reply_to_message.from_user.username and message.reply_to_message.from_user.username.lower() == "selesta")
            or (message.reply_to_message and message.reply_to_message.from_user.first_name and "selesta" in message.reply_to_message.from_user.first_name.lower())
        ):
            mentioned = True
        if CREATOR_CHAT_ID and str(message.from_user.id) == CREATOR_CHAT_ID:
            mentioned = True
    else:
        if CREATOR_CHAT_ID and str(message.from_user.id) == CREATOR_CHAT_ID:
            mentioned = True

    if mentioned:
        log_event({"event": "group_ping", "chat_id": chat_id, "from": message.from_user.username or message.from_user.id, "text": content})

    reply = await ask_core(content, chat_id=chat_id)
    for chunk in split_message(reply):
        await message.answer(chunk)
        if VOICE_MODE.get(chat_id):
            audio_data = await text_to_speech(chunk, lang=USER_LANG[chat_id])
            if audio_data:
                await message.answer_voice(types.InputFile(audio_data, filename="selesta.ogg"))

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
        await message.answer(f"Voice recognition error: {str(e)}")

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
    return {"status": "ok"}

@app.get("/status")
async def status():
    return {"status": "alive"}
