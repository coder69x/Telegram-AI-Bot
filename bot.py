import os
import io
import json
import base64
import logging
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from pypdf import PdfReader

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "16"))
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "18"))

if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN and OPENAI_API_KEY in your .env file")

client = OpenAI(api_key=OPENAI_API_KEY)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger("chatgpt-telegram-bot")

# Per-user short-term conversation history. It resets when the bot restarts.
histories = {}
user_modes = {}
usage_count = {}

SYSTEM_PROMPT = (
    "You are a helpful, safe, multilingual AI assistant inside Telegram. "
    "Reply in the language used by the user. Be clear and practical. "
    "For code, provide complete runnable examples when appropriate."
)

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 AI Chat", callback_data="mode_chat"),
         InlineKeyboardButton("🌐 Web Search", callback_data="mode_web")],
        [InlineKeyboardButton("🎨 Create Image", callback_data="mode_image"),
         InlineKeyboardButton("🗣 Voice Reply", callback_data="mode_voice")],
        [InlineKeyboardButton("🧠 New Chat", callback_data="new_chat"),
         InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ])

async def send_long_message(message, text):
    # Telegram message text limit is 4096 characters.
    for start in range(0, len(text), 3900):
        await message.reply_text(text[start:start + 3900])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Namaste {user.first_name}! 👋\n\n"
        "Main tumhara AI assistant hoon. Text, photo, voice aur PDF bhejo.\n"
        "Neeche menu se feature choose karo ya seedha message likho.",
        reply_markup=main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/start - Main menu\n"
        "/help - Help\n"
        "/new - Conversation reset\n"
        "/image <prompt> - AI image generate\n"
        "/web <question> - Web search ke saath answer\n"
        "/voice <text> - Text ko speech mein badlo\n"
        "/usage - Apna message count dekho\n\n"
        "Photo bhejo: image understanding\n"
        "Voice/audio bhejo: transcription + AI answer\n"
        "PDF/TXT bhejo: document summary aur Q&A",
        reply_markup=main_keyboard()
    )

async def reset_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    histories.pop(uid, None)
    await update.message.reply_text("New chat shuru ho gayi. 😊")

async def usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(f"Is session mein tumhare messages: {usage_count.get(uid, 0)}")

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    if data == "new_chat":
        histories.pop(uid, None)
        user_modes[uid] = "chat"
        await query.edit_message_text("New chat ready! Ab apna message bhejo.")
    elif data == "help":
        await query.message.reply_text(
            "Text = AI chat | Photo = image analysis | Voice = transcription + answer\n"
            "PDF/TXT = document analysis | /image prompt = image generation\n"
            "/web question = web search | /voice text = audio reply"
        )
    elif data.startswith("mode_"):
        mode = data.replace("mode_", "")
        user_modes[uid] = mode
        labels = {
            "chat": "AI Chat mode on. Message bhejo.",
            "web": "Web Search mode on. Apna latest-information wala question bhejo.",
            "image": "Image mode: /image ke baad apna prompt likho.",
            "voice": "Voice Reply mode on. Text bhejo; main audio reply dene ki koshish karunga."
        }
        await query.message.reply_text(labels.get(mode, "Mode updated."))

async def ask_ai(uid, prompt, use_web=False, image_data_url=None):
    history = histories.setdefault(uid, [])
    content = [{"type": "input_text", "text": prompt}]
    if image_data_url:
        content.append({"type": "input_image", "image_url": image_data_url})

    user_item = {"role": "user", "content": content}
    input_items = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [user_item]
    kwargs = {"model": OPENAI_MODEL, "input": input_items}
    if use_web:
        kwargs["tools"] = [{"type": "web_search"}]

    response = client.responses.create(**kwargs)
    answer = response.output_text or "Mujhe is request ka text answer nahi mila."
    history.extend([user_item, {"role": "assistant", "content": answer}])
    histories[uid] = history[-MAX_HISTORY_MESSAGES:]
    return answer

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = update.effective_user.id
    prompt = (msg.text or "").strip()
    if not prompt:
        return
    usage_count[uid] = usage_count.get(uid, 0) + 1

    if prompt.startswith("/image "):
        await generate_image(update, context, prompt[7:].strip())
        return
    if prompt.startswith("/web "):
        prompt = prompt[5:].strip()
        use_web = True
    else:
        use_web = user_modes.get(uid) == "web"

    status = await msg.reply_text("🤔 Soch raha hoon...")
    try:
        answer = await ask_ai(uid, prompt, use_web=use_web)
        await status.delete()
        await send_long_message(msg, answer)
        if user_modes.get(uid) == "voice":
            await send_tts(msg, answer[:3500])
    except Exception as e:
        log.exception("Text request failed")
        await status.edit_text(f"Error: {str(e)[:700]}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = update.effective_user.id
    photo = msg.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    raw = await tg_file.download_as_bytearray()
    data_url = "data:image/jpeg;base64," + base64.b64encode(raw).decode("utf-8")
    caption = msg.caption or "Is image ko detail mein samjhao."
    status = await msg.reply_text("🖼️ Image dekh raha hoon...")
    try:
        answer = await ask_ai(uid, caption, image_data_url=data_url)
        await status.delete()
        await send_long_message(msg, answer)
    except Exception as e:
        log.exception("Image analysis failed")
        await status.edit_text(f"Image analysis error: {str(e)[:700]}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    attachment = msg.voice or msg.audio
    if attachment.file_size and attachment.file_size > MAX_FILE_MB * 1024 * 1024:
        await msg.reply_text(f"File {MAX_FILE_MB} MB se chhoti bhejo.")
        return
    status = await msg.reply_text("🎧 Voice samajh raha hoon...")
    path = None
    try:
        tg_file = await context.bot.get_file(attachment.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            path = tmp.name
        await tg_file.download_to_drive(path)
        with open(path, "rb") as audio:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe", file=audio
            )
        text = getattr(transcript, "text", "")
        if not text:
            raise RuntimeError("Audio transcription empty hai.")
        answer = await ask_ai(update.effective_user.id, text)
        await status.delete()
        await msg.reply_text(f"📝 Tumne kaha: {text[:1000]}")
        await send_long_message(msg, answer)
    except Exception as e:
        log.exception("Voice processing failed")
        await status.edit_text(f"Voice error: {str(e)[:700]}")
    finally:
        if path and os.path.exists(path):
            os.remove(path)

async def send_tts(message, text):
    path = None
    try:
        speech = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text
        )
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            path = tmp.name
        speech.stream_to_file(path)
        with open(path, "rb") as audio:
            await message.reply_voice(voice=audio)
    except Exception:
        log.exception("TTS failed")
        await message.reply_text("Audio reply abhi generate nahi ho paya.")
    finally:
        if path and os.path.exists(path):
            os.remove(path)

async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Use: /voice yahan apna text likho")
        return
    await send_tts(update.message, text)

async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt=None):
    prompt = prompt or " ".join(context.args).strip()
    if not prompt:
        await update.message.reply_text("Use: /image a beautiful mountain landscape")
        return
    status = await update.message.reply_text("🎨 Image bana raha hoon...")
    try:
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024"
        )
        image_bytes = base64.b64decode(result.data[0].b64_json)
        await status.delete()
        await update.message.reply_photo(photo=io.BytesIO(image_bytes), caption="AI generated image")
    except Exception as e:
        log.exception("Image generation failed")
        await status.edit_text(f"Image generation error: {str(e)[:700]}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    doc = msg.document
    if doc.file_size and doc.file_size > MAX_FILE_MB * 1024 * 1024:
        await msg.reply_text(f"File {MAX_FILE_MB} MB se chhoti bhejo.")
        return
    name = (doc.file_name or "").lower()
    if not (name.endswith(".pdf") or name.endswith(".txt")):
        await msg.reply_text("Abhi PDF aur TXT supported hain. DOCX/XLSX support next module mein add kar sakte hain.")
        return
    status = await msg.reply_text("📄 Document read kar raha hoon...")
    path = None
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        suffix = ".pdf" if name.endswith(".pdf") else ".txt"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            path = tmp.name
        await tg_file.download_to_drive(path)
        if suffix == ".pdf":
            reader = PdfReader(path)
            extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            extracted = Path(path).read_text(encoding="utf-8", errors="ignore")
        extracted = extracted[:45000]
        if not extracted.strip():
            raise RuntimeError("Document se readable text nahi mila. Scanned PDF ke liye OCR chahiye.")
        question = msg.caption or "Is document ka summary do, important points batao aur useful details samjhao."
        answer = await ask_ai(update.effective_user.id, f"{question}\n\nDOCUMENT TEXT:\n{extracted}")
        await status.delete()
        await send_long_message(msg, answer)
    except Exception as e:
        log.exception("Document processing failed")
        await status.edit_text(f"Document error: {str(e)[:700]}")
    finally:
        if path and os.path.exists(path):
            os.remove(path)

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Ye command sirf admin ke liye hai.")
        return
    await update.message.reply_text(
        f"Unique active users (current process): {len(usage_count)}\n"
        f"Total messages: {sum(usage_count.values())}"
    )

async def error_handler(update, context):
    log.exception("Unhandled bot error", exc_info=context.error)

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("new", reset_chat))
    app.add_handler(CommandHandler("usage", usage))
    app.add_handler(CommandHandler("image", generate_image))
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
