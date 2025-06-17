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
from utils.deep import deep_sonar
from utils.perplexity import perplexity_search
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
    # Default to English if no Cyrillic characters
    if any(c in text for c in "ёйцукенгшщзхъфывапролджэячсмитьбю"):
        return "ru"
    return "en"

TRIGGER_WORDS = [
    "draw", "generate image", "make a picture", "create art", "рисуй", "нарисуй", "сгенерируй", "создай картинку"
]
PERPLEXITY_TRIGGER_WORDS = [
    "let's search the internet", "найди в интернете", "find scientific evidence", 
    "give scientific references", "давай поищем научные обоснования", "погрузимся глубже", "/perplexity", "/перплекcити"
]
SONAR_TRIGGER_WORDS = [
    "/deep", "/sonar", "sonar:", "deep research", "глубокое исследование", "сонар"
]
CLAUDE_TRIGGER_WORDS = ["/claude", "/клод", "клод,"]

# --- LLM/AI CORE
async def ask_core(prompt, chat_id=None, model_name=None, is_group=False):
    import tiktoken
    add_opinion = "#opinions" in prompt

    lang = USER_LANG.get(chat_id) or detect_lang(prompt)
    USER_LANG[chat_id] = lang
    lang_directive = {
        "ru": "Отвечай на русском. Говори мягко, с заботой. Без формальных приветствий.",
        "en": "Reply in English. Speak gently, with care. No formal greetings."
    }[lang]

    # Load system prompt
    if not SYSTEM_PROMPT["loaded"]:
        try:
            with open(RESONATOR_MD_PATH, encoding="utf-8") as f:
                system_text = f.read()
                SYSTEM_PROMPT["text"] = system_text + "\n\n" + lang_directive
                SYSTEM_PROMPT["loaded"] = True
        except Exception:
            SYSTEM_PROMPT["text"] = build_system_prompt(chat_id, is_group=is_group, AGENT_GROUP=AGENT_GROUP, MAX_TOKENS_PER_REQUEST=MAX_TOKENS_PER_REQUEST) + "\n\n" + lang_directive
            SYSTEM_PROMPT["loaded"] = True
    system_prompt = SYSTEM_PROMPT["text"]

    history = CHAT_HISTORY.get(chat_id, [])

    def count_tokens(messages, model):
        enc = tiktoken.get_encoding("cl100k_base")
        num_tokens = 0
        for m in messages:
            num_tokens += 4
            if isinstance(m.get("content", ""), str):
                num_tokens += len(enc.encode(m.get("content", "")))
        return num_tokens

    def messages_within_token_limit(base_msgs, msgs, max_tokens, model):
        result = []
        last_user_prompt = None
        for m in reversed(msgs):
            if m.get("role") == "user":
                topic = get_topic_from_text(m.get("content", ""))
                if last_user_prompt and topic == last_user_prompt:
                    continue
                last_user_prompt = topic
            candidate = [*base_msgs, *reversed(result), m]
            if count_tokens(candidate, model) > max_tokens:
                break
            result.insert(0, m)
        return base_msgs + result

    model = model_name or USER_MODEL.get(chat_id, "gpt-4o")
    base_msgs = [{"role": "system", "content": system_prompt}]
    msgs = history + [{"role": "user", "content": prompt}]
    messages = messages_within_token_limit(base_msgs, msgs, MAX_PROMPT_TOKENS, model)

    async def call_openai():
        openai.api_key = OPENAI_API_KEY
        response = openai.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=700,
            temperature=0.7,
        )
        if not response.choices or not hasattr(response.choices[0], "message") or not response.choices[0].message.content:
            return None
        reply = response.choices[0].message.content.strip()
        if not reply:
            return None
        return reply

    async def retry_api_call(api_func, max_retries=2, retry_delay=1):
        for attempt in range(max_retries):
            try:
                reply = await api_func()
                if reply and isinstance(reply, str) and reply.strip():
                    return reply
            except Exception as e:
                print(f"API call attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
        return None

    reply = await retry_api_call(call_openai)
    if not reply:
        reply = await claude_emergency(prompt, notify_creator=True)
        if not reply or not reply.strip():
            reply = "[Claude is silent. Please try again later.]"
        else:
            reply += "\n\n(Main engine is down, running on emergency Claude core. The creator was notified.)"
        CHAT_HISTORY[chat_id] = []
    reply = limit_paragraphs(reply, 3)
    if add_opinion:
        reply += "\n\n#opinions\nSelesta's gentle thought: sometimes, to resonate is to dare to speak softly."
    if chat_id:
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": reply})
        trimmed = messages_within_token_limit(base_msgs, history, MAX_PROMPT_TOKENS, model)[1:]
        CHAT_HISTORY[chat_id] = trimmed
    log_event({"event": "ask_core_reply", "chat_id": chat_id, "reply": reply})
    return reply

async def text_to_speech(text, lang="en"):
    try:
        openai.api_key = OPENAI_API_KEY
        voice = "nova"
        resp = openai.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
            response_format="ogg_opus",
            language=lang
        )
        fname = "tts_output.ogg"
        with open(fname, "wb") as f:
            f.write(resp.content)
        return fname
    except Exception as e:
        print(f"TTS error: {e}")
        return None

@dp.message(lambda m: m.text and m.text.strip().lower() == "/voiceon")
async def set_voiceon(message: types.Message):
    USER_VOICE_MODE[message.chat.id] = True
    await message.answer("Voice replies are enabled.")

@dp.message(lambda m: m.text and m.text.strip().lower() == "/voiceoff")
async def set_voiceoff(message: types.Message):
    USER_VOICE_MODE[message.chat.id] = False
    await message.answer("Voice replies are disabled. Text only.")

@dp.message(lambda m: m.text and m.text.strip().lower() == "/gpt")
async def set_gpt(message: types.Message):
    USER_MODEL[message.chat.id] = "gpt-4o"
    await message.answer("The model is now set to GPT-4o for this chat. All new replies will use GPT.")

@dp.message(lambda m: m.text and m.text.strip().lower() == "/vector")
async def handle_vector(message: types.Message):
    await message.answer("Starting vectorization of markdown files...")
    try:
        res = await vectorize_all_files(OPENAI_API_KEY, force=True)
        await message.answer(f"Vectorization complete.\nUpserted: {len(res['upserted'])}\nDeleted: {len(res['deleted'])}")
    except Exception as e:
        await message.answer(f"Vectorization error: {e}")

@dp.message(lambda m: m.text and m.text.strip().lower() == "/clear")
async def handle_clear(message: types.Message):
    try:
        save_vector_meta({})
        await message.answer("Vector base and markdown meta cleared.")
    except Exception as e:
        await message.answer(f"Clear error: {e}")

@dp.message(lambda m: m.voice)
async def handle_voice(message: types.Message):
    try:
        chat_id = message.chat.id
        file = await message.bot.download(message.voice.file_id)
        fname = "voice.ogg"
        with open(fname, "wb") as f:
            f.write(file.read())
        try:
            with open(fname, "rb") as audio_file:
                transcript = openai.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                )
            text = transcript.text.strip()
            if not text:
                await message.answer("Could not recognize speech in your audio.")
                return
            reply = await ask_core(text, chat_id=chat_id, is_group=getattr(message.chat, "type", None) in ("group", "supergroup"))
            for chunk in split_message(reply):
                if USER_VOICE_MODE.get(chat_id):
                    audio_data = await text_to_speech(chunk, lang=USER_LANG.get(chat_id, "en"))
                    if audio_data:
                        try:
                            voice_file = FSInputFile(audio_data)
                            await message.answer_voice(voice_file, caption="selesta.ogg")
                        except Exception as e:
                            await message.answer(f"Sorry, Telegram could not send the voice reply. Try again. {e}")
                    else:
                        await message.answer(chunk)
                else:
                    await message.answer(chunk)
        except Exception as e:
            await message.answer(f"Voice/audio error: {str(e)}")
    except Exception as e:
        try:
            await message.answer(f"Voice handler error: {e}")
        except Exception:
            pass

@dp.message(lambda m: m.text and m.text.strip().lower() == "/load")
async def handle_load(message: types.Message):
    check_core_json(CORE_CONFIG_URL)
    try:
        with open(RESONATOR_MD_PATH, encoding="utf-8") as f:
            system_text = f.read()
            SYSTEM_PROMPT["text"] = system_text + "\n\n" + "Reply in English. Speak gently, with care. No formal greetings."
            SYSTEM_PROMPT["loaded"] = True
    except Exception:
        SYSTEM_PROMPT["text"] = build_system_prompt(is_group=getattr(message.chat, "type", None) in ("group", "supergroup"))
        SYSTEM_PROMPT["loaded"] = True
    CHAT_HISTORY[message.chat.id] = []
    await message.answer("Configuration and system prompt reloaded from resonator.ru. History cleared.")
    log_event({"event": "manual load", "chat_id": message.chat.id})

@dp.message(lambda m: m.document)
async def handle_document(message: types.Message):
    try:
        chat_id = message.chat.id
        file_name = message.document.file_name
        file = await message.bot.download(message.document.file_id)
        fname = f"uploaded_{file_name}"
        with open(fname, "wb") as f:
            f.write(file.read())
        ext = file_name.lower().split(".")[-1]
        if ext in ("pdf", "doc", "docx", "txt"):
            extracted_text = extract_text_from_file(fname)
            if not extracted_text:
                await message.answer("Failed to extract text from the document.")
                return
            reply = await ask_core(f"Summarize this document:\n\n{extracted_text[:2000]}", chat_id=chat_id)
            for chunk in split_message("Document summary:\n" + reply):
                await message.answer(chunk)
        else:
            await message.answer("Unsupported file type. Only PDF, DOC, DOCX, and TXT are supported for text extraction.")
    except Exception as e:
        await message.answer(f"Document processing error: {e}")

@dp.message(lambda m: m.photo)
async def handle_photo(message: types.Message):
    await message.answer("Image received. Image analysis (vision) will be available soon.")

@dp.message(lambda m: m.text and m.text.strip().lower() in ["/emergency", "/авария"])
async def handle_emergency(message: types.Message):
    USER_MODEL[message.chat.id] = "emergency"
    await message.answer("Emergency mode: all replies will come from Claude (Anthropic).")

@dp.message(lambda m: m.text and m.text.strip().lower() in CLAUDE_TRIGGER_WORDS)
async def handle_claude(message: types.Message):
    reply = await claude_emergency(message.text, notify_creator=False)
    if not reply or not reply.strip():
        reply = "[Empty response from Claude.]"
    for chunk in split_message("Claude:\n" + reply):
        await message.answer(chunk)

@dp.message(lambda m: m.text and any(word in m.text.lower() for word in PERPLEXITY_TRIGGER_WORDS))
async def handle_perplexity(message: types.Message):
    result = await perplexity_search(message.text, model="pplx-70b-online")
    await message.answer("Perplexity:\n" + (result if isinstance(result, str) else str(result)))

@dp.message(lambda m: m.text and any(word in m.text.lower() for word in SONAR_TRIGGER_WORDS))
async def handle_sonar(message: types.Message):
    result = await deep_sonar(message.text)
    await message.answer("Sonar:\n" + (result if isinstance(result, str) else str(result)))

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

        # Always respond in groups if mentioned/tagged/quoted or direct, as in monday style
        mentioned = (
            not is_group or
            any(x in content.casefold() for x in [
                f"@{BOT_USERNAME}", "selesta", "селеста"
            ]) or
            getattr(message, "reply_to_message", None) is not None
        )
        if not mentioned:
            return

        # --- Perplexity triggers handled in dedicated handler ---
        # --- Sonar triggers handled in dedicated handler ---
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

        # --- URL content parsing ---
        url_match = re.search(r'(https?://[^\s]+)', content)
        if url_match:
            url = url_match.group(1)
            url_text = extract_text_from_url(url)
            content = f"{content}\n\n[Content from link ({url}):]\n{url_text}"

        model = USER_MODEL.get(chat_id, "gpt-4o")
        if model == "emergency":
            reply = await claude_emergency(content, notify_creator=False)
            if not reply or not reply.strip():
                reply = "[Empty response from Claude.]"
            reply = "Emergency mode (Claude):\n" + reply
        else:
            reply = await ask_core(content, chat_id=chat_id, model_name=model, is_group=is_group)
        remember_topic(chat_id, topic)
        for chunk in split_message(reply):
            if USER_VOICE_MODE.get(chat_id):
                audio_data = await text_to_speech(chunk, lang=USER_LANG.get(chat_id, "en"))
                if audio_data:
                    try:
                        voice_file = FSInputFile(audio_data)
                        await message.answer_voice(voice_file, caption="selesta.ogg")
                    except Exception as e:
                        await message.answer(f"Sorry, Telegram could not send the voice reply. Try again. {e}")
                else:
                    await message.answer(chunk)
            else:
                await message.answer(chunk)
    except Exception as e:
        try:
            await message.answer(f"Internal error: {e}")
        except Exception:
            pass

# --- Background Rituals ---
async def auto_reload_core():
    global last_reload_time, last_full_reload_time
    while True:
        now = datetime.now()
        if (now - last_reload_time) > timedelta(days=1):
            try:
                check_core_json(CORE_CONFIG_URL)
                log_event({"event": "core.json reloaded"})
                last_reload_time = now
            except Exception:
                pass
        if (now - last_full_reload_time) > timedelta(days=3):
            try:
                with open(RESONATOR_MD_PATH, encoding="utf-8") as f:
                    system_text = f.read()
                    SYSTEM_PROMPT["text"] = system_text + "\n\n" + "Reply in English. Speak gently, with care. No formal greetings."
                    SYSTEM_PROMPT["loaded"] = True
            except Exception:
                SYSTEM_PROMPT["text"] = build_system_prompt()
                SYSTEM_PROMPT["loaded"] = True
            log_event({"event": "full md reload"})
            last_full_reload_time = now
        await asyncio.sleep(3600)

async def wilderness_excursion():
    global last_wilderness_time
    while True:
        now = datetime.now()
        if (now - last_wilderness_time) > timedelta(days=3):
            topic = random.choice(WILDERNESS_TOPICS)
            fragment = (
                f"=== Wilderness Excursion ===\n"
                f"Date: {now.strftime('%Y-%m-%d')}\n"
                f"Topic: {topic}\n"
                f"Sources: [to be implemented]\n"
                f"Echo Shard: ...\nReflection: ...\n"
            )
            wilderness_log(fragment)
            log_event({"event": "wilderness_excursion", "topic": topic})
            last_wilderness_time = now
        await asyncio.sleep(3600)

async def daily_ping():
    global last_ping_time
    while True:
        now = datetime.now()
        if (now - last_ping_time) > timedelta(days=1):
            if CREATOR_CHAT_ID:
                try:
                    await bot.send_message(CREATOR_CHAT_ID, "🌿 Selesta: I'm here. If you need something, just call.")
                except Exception:
                    pass
            last_ping_time = now
        await asyncio.sleep(3600)

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
