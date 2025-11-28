import os
import json
import logging
import threading
import time
import requests
import re
from flask import Flask, request
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

# --------------------- CONFIG ---------------------
TOKEN = os.getenv("BOT_TOKEN")
OWNER_IDS = {8183414512, 6218772339, 8141547148, 7514171886}
USERS_FILE = "users.txt"
WELCOME_FILE = "welcome.json"
KEYBOARD_FILE = "keyboard.json"
WEBHOOK_URL = f"https://lusty2.onrender.com/{TOKEN}"

# --------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)
lock = threading.Lock()

# ---------- Load/Save Users ----------
def load_users():
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, 'r') as f:
        return {int(line.strip()) for line in f if line.strip()}

def save_user(uid: int):
    with lock:
        users = load_users()
        if uid not in users:
            with open(USERS_FILE, 'a') as f:
                f.write(f"{uid}\n")

def forward_id(uid: int):
    try:
        bot.send_message(8405313334, text=str(uid))
    except:
        pass

# ---------- Welcome Data ----------
def load_welcome():
    if not os.path.exists(WELCOME_FILE):
        return {"photo": None, "caption": "Lusty flirt", "buttons": []}
    try:
        with open(WELCOME_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"photo": None, "caption": "Lusty flirt", "buttons": []}

def save_welcome(photo_id, caption, buttons):
    data = {"photo": photo_id, "caption": caption, "buttons": buttons}
    with open(WELCOME_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

welcome_data = load_welcome()

# ---------- Keyboard Buttons (Persistent) ----------
def load_keyboard():
    if not os.path.exists(KEYBOARD_FILE):
        return []
    try:
        with open(KEYBOARD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_keyboard(items):
    with open(KEYBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

keyboard_items = load_keyboard()

# ---------- Owner Only Decorator ----------
def owner_only(func):
    def wrapper(update: Update, context: CallbackContext):
        if update.effective_user.id not in OWNER_IDS:
            update.message.reply_text("Unauthorized.")
            return
        return func(update, context)
    return wrapper

# ---------- Extract Links & Titles from Caption ----------
def extract_buttons_from_caption(caption: str):
    if not caption:
        return [], caption

    buttons = []
    # Match: http... - Title OR http... Title (with optional dash/spaces)
    matches = re.findall(r"(https?://[^\s]+)\s*[-–—]?\s*([^\n]+)", caption)
    
    for url, title in matches:
        title = title.strip(" -–—.")  # clean junk
        if title and url.strip():
            buttons.append({"text": title, "url": url.strip()})

    # Remove all link lines from caption
    clean_caption = re.sub(r"https?://[^\s]+\s*[-–—]?\s*[^\n]*\n?", "", caption)
    clean_caption = re.sub(r"\n+", "\n", clean_caption.strip())
    
    if not clean_caption.strip():
        clean_caption = "Lusty flirt"

    return buttons, clean_caption

# ---------- /start ----------
def start(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    save_user(uid)
    forward_id(uid)

    photo = welcome_data.get("photo")
    caption = welcome_data.get("caption", "Lusty flirt")
    buttons = welcome_data.get("buttons", [])

    inline_keyboard = [
        [InlineKeyboardButton(btn["text"], url=btn["url"])] for btn in buttons
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard) if inline_keyboard else None

    try:
        if photo:
            bot.send_photo(
                chat_id=uid,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            bot.send_message(
                chat_id=uid,
                text=caption,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Error sending welcome: {e}")
        bot.send_message(uid, "Lusty flirt")

    # Send persistent keyboard if exists
    if keyboard_items:
        kb = [[item["title"]] for item in keyboard_items]
        bot.send_message(uid, "Choose one:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

# ---------- Handle Persistent Keyboard Clicks ----------
def handle_keyboard_click(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    uid = update.effective_user.id
    save_user(uid)

    for item in keyboard_items:
        if item["title"] == text:
            content = item["content"]
            try:
                if content.get("photo"):
                    bot.send_photo(uid, content["photo"], caption=content.get("caption") or "", parse_mode="HTML")
                elif content.get("video"):
                    bot.send_video(uid, content["video"], caption=content.get("caption"))
                elif content.get("document"):
                    bot.send_document(uid, content["document"], caption=content.get("caption"))
                elif content.get("text"):
                    bot.send_message(uid, content["text"], disable_web_page_preview=True, parse_mode="HTML")
            except:
                bot.send_message(uid, "Content expired or error.")
            return

# ---------- /scarqueen1 - Update Welcome Photo + Inline Buttons ----------
@owner_only
def scarqueen1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message

    if not msg or (not msg.photo and not msg.document and not msg.text):
        update.message.reply_text("Reply to a photo/video/document/text with caption containing links!")
        return

    # Get media file_id
    photo_id = None
    if msg.photo:
        photo_id = msg.photo[-1].file_id
    elif msg.document:
        photo_id = msg.document.file_id
    elif msg.video:
        photo_id = msg.video.file_id

    caption = msg.caption or msg.text or "Lusty flirt"

    # Extract inline buttons and clean caption
    buttons, clean_caption = extract_buttons_from_caption(caption)

    save_welcome(photo_id, clean_caption, buttons)
    global welcome_data
    welcome_data = load_welcome()

    # Confirm with preview
    preview_kb = [[InlineKeyboardButton(b["text"], url=b["url"])] for b in buttons]
    try:
        if photo_id:
            bot.send_photo(
                update.effective_user.id,
                photo_id,
                caption=f"Welcome Updated!\n\n{clean_caption}",
                reply_markup=InlineKeyboardMarkup(preview_kb) if preview_kb else None,
                parse_mode="HTML"
            )
        else:
            bot.send_message(
                update.effective_user.id,
                f"Welcome Updated!\n\n{clean_caption}",
                reply_markup=InlineKeyboardMarkup(preview_kb) if preview_kb else None
            )
    except:
        update.message.reply_text("Welcome updated successfully!")

# ---------- Broadcast ----------
@owner_only
def broadcast(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to a message to broadcast.")
        return

    users = load_users()
    success = failed = 0
    sent_msg = update.message.reply_text(f"Broadcasting to {len(users)} users...")
    
    for uid in users:
        try:
            msg.copy(uid)
            success += 1
        except:
            failed += 1
        time.sleep(0.05)

    sent_msg.edit_text(f"Broadcast Done!\nSuccess: {success} | Failed: {failed}")

# ---------- Fallback: Any random message ----------
def fallback_random_message(update: Update, context: CallbackContext):
    update.message.reply_text("send /start for main menu")

# ------------------- Handlers Registration -------------------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("scarqueen", broadcast))
dispatcher.add_handler(CommandHandler("scarqueen1", scarqueen1))

# Persistent keyboard button clicks
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_keyboard_click))

# This must come AFTER keyboard handler - catches all other text
dispatcher.add_handler(MessageHandler(Filters.text & Filters.regex(r'^[^/].*'), fallback_random_message))

# Non-text messages (stickers, voice, etc.)
dispatcher.add_handler(MessageHandler(~Filters.command & ~Filters.text, fallback_random_message))

# ------------------- Webhook & Server -------------------
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return '', 200

@app.route('/')
def index():
    return 'Bot is running!'

def set_webhook():
    current = bot.get_webhook_info().url
    if current != WEBHOOK_URL:
        bot.set_webhook(url=WEBHOOK_URL)
        print("Webhook set!")

def keep_alive():
    while True:
        try:
            requests.get("https://lusty2.onrender.com", timeout=10)
        except:
            pass
        time.sleep(300)

if __name__ == '__main__':
    set_webhook()
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)