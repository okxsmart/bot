import os
import uuid
import asyncio
import logging
import json
import subprocess
import whisper
import threading
import aiohttp
from quart import Quart, render_template, request, jsonify
from dotenv import load_dotenv
from pydub import AudioSegment
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler, ContextTypes, filters
)

# === 🔑 Завантаження .env ===
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
USE_OPENAI = os.getenv("USE_OPENAI", "false").lower() == "true"
FFMPEG_PATH = "ffmpeg"

# === Логи ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Завантаження Whisper...")
whisper_model = whisper.load_model("base")

# === Моделі ===
GROQ_MODELS = [
    ("LLaMA 3 (8B)", "llama3-8b-8192"),
    ("LLaMA 4 Maverick (17B)", "meta-llama/llama-4-maverick-17b-128e-instruct"),
    ("LLaMA 3 (70B)", "llama3-70b-8192"),
    ("DeepSeek Distill 70B", "deepseek-r1-distill-llama-70b"),
    ("Gemma 2 (9B IT)", "gemma2-9b-it")
]

# === 🌐 Quart app ===
app = Quart(__name__)

@app.route("/")
async def index():
    return await render_template("index.html", models=GROQ_MODELS)

@app.route("/process_audio", methods=["POST"])
async def process_audio():
    files = await request.files
    if "audio" not in files:
        return jsonify({"error": "Немає аудіофайлу"}), 400

    file = files["audio"]
    temp_input = f"temp_{uuid.uuid4().hex}.webm"
    temp_output = f"temp_{uuid.uuid4().hex}.wav"

    try:
        await file.save(temp_input)
        audio = AudioSegment.from_file(temp_input)
        if len(audio) < 1000:
            return jsonify({"error": "Аудіо занадто коротке"}), 400

        subprocess.run([FFMPEG_PATH, "-i", temp_input, "-ac", "1", "-ar", "16000", temp_output], check=True)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: whisper_model.transcribe(temp_output, language="uk"))
        user_text = result.get("text", "").strip()

        if not user_text or len(user_text) < 5:
            return jsonify({"error": "Не вдалося розпізнати змістовний текст"}), 400

        form = await request.form
        model_name = form.get("model", GROQ_MODELS[0][0])
        model_id = next((m[1] for m in GROQ_MODELS if m[0] == model_name), GROQ_MODELS[0][1])

        reply = await get_ai_response(user_text, model_id)
        if not reply:
            return jsonify({"error": "Помилка AI"}), 500

        return jsonify({"text": reply})

    finally:
        for f in [temp_input, temp_output]:
            if os.path.exists(f):
                os.remove(f)

@app.route("/process_text", methods=["POST"])
async def process_text():
    form = await request.form
    user_text = form.get("text", "")
    if not user_text:
        return jsonify({"error": "Текст не надіслано"}), 400

    model_name = form.get("model", GROQ_MODELS[0][0])
    model_id = next((m[1] for m in GROQ_MODELS if m[0] == model_name), GROQ_MODELS[0][1])

    reply = await get_ai_response(user_text, model_id)
    if not reply:
        return jsonify({"error": "AI не відповів"}), 500

    return jsonify({"text": reply})

# === AI: Groq або OpenAI ===
async def get_ai_response(prompt, model, retries=3):
    if USE_OPENAI:
        return await get_openai_response(prompt, model)
    else:
        return await get_groq_response(prompt, model, retries)

async def get_groq_response(prompt, model, retries=3):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Ти голосовий асистент."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4,
        "top_p": 0.9,
        "stream": False
    }

    for attempt in range(1, retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data["choices"][0]["message"]["content"].strip()
                    elif response.status in (429, 502, 503):
                        await asyncio.sleep(2 * attempt)
        except Exception as e:
            logging.error(f"Groq error: {e}")
            await asyncio.sleep(2 * attempt)

    return None

async def get_openai_response(prompt, model):
    return "[OpenAI відповіді ще не реалізовані]"

# === ✅ Telegram Webhook Bot ===
telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

async def telegram_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    logger.info(f"Отримано текстове повідомлення від користувача: {user_text}")
    reply = await get_ai_response(user_text, GROQ_MODELS[0][1])
    logger.info(f"Відповідь AI: {reply}")
    await update.message.reply_text(reply or "❌ Помилка.")

async def telegram_voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice_file = await update.message.voice.get_file()
    temp_path = f"temp_{uuid.uuid4()}.ogg"
    await voice_file.download_to_drive(temp_path)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: whisper_model.transcribe(temp_path, language="uk"))
    os.remove(temp_path)

    text = result.get("text", "").strip()
    if not text:
        await update.message.reply_text("Не вдалося розпізнати голос.")
        return

    logger.info(f"Розпізнаний текст з голосового повідомлення: {text}")
    reply = await get_ai_response(text, GROQ_MODELS[0][1])
    logger.info(f"Відповідь AI на голосове повідомлення: {reply}")
    await update.message.reply_text(reply or "❌ Помилка.")

# Додаємо обробники
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_text_handler))
telegram_app.add_handler(MessageHandler(filters.VOICE, telegram_voice_handler))

@app.before_serving
async def startup():
    logger.info(f"Встановлення Webhook: {WEBHOOK_URL}")
    try:
        await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
        await telegram_app.start()
        logger.info(f"📡 Webhook успішно встановлено: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Помилка при встановленні Webhook: {e}", exc_info=True)
        raise Exception("Не вдалося встановити Webhook")
        
@app.after_serving
async def shutdown():
    await telegram_app.stop()
    logger.info("🛑 Webhook зупинено")
    
@app.route("/webhook", methods=["POST"])
async def telegram_webhook():
    try:
        data = await request.get_data()
        text_data = data.decode("utf-8")
        logger.info(f"Webhook отримав: {text_data}")

        # Перетворюємо отримані дані в JSON
        json_data = json.loads(text_data)  # Перетворення рядка в JSON
        update = Update.de_json(json_data, telegram_app.bot)

        await telegram_app.update_queue.put(update)
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Помилка в webhook: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500

# === Функція старту Telegram бота ===
def start_telegram_bot():
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)

    asyncio.set_event_loop(asyncio.new_event_loop())  # Створюємо новий event loop

    telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_text_handler))
    telegram_app.add_handler(MessageHandler(filters.VOICE, telegram_voice_handler))

    logger.info("✅ Telegram-бот запущено!")
    telegram_app.run_polling()  # Запуск бота на polling режимі (можна замінити на webhook якщо потрібно)

# Запуск Telegram бота в окремому потоці
threading.Thread(target=start_telegram_bot).start()

# ▶️ Запуск
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
