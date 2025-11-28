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

# ---------- Load/Save Welcome ----------
def load_welcome():
    if not os.path.exists(WELCOME_FILE):
        return {"photo": None, "caption": "Welcome!", "buttons": []}
    try:
        with open(WELCOME_FILE, "r") as f:
            return json.load(f)
    except:
        return {"photo": None, "caption": "Welcome!", "buttons": []}

def save_welcome(photo_id, caption, buttons):
    data = {"photo": photo_id, "caption": caption, "buttons": buttons}
    with open(WELCOME_FILE, "w") as f:
        json.dump(data, f)

welcome_data = load_welcome()

# ---------- Load/Save Reply Keyboard ----------
def load_reply_keyboard():
    if not os.path.exists(KEYBOARD_FILE):
        return []
    try:
        with open(KEYBOARD_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_reply_keyboard(buttons):
    with open(KEYBOARD_FILE, "w") as f:
        json.dump(buttons, f)

reply_keyboard_buttons = load_reply_keyboard()

# ---------- Users ----------
def load_users():
    if not os.path.exists(USERS_FILE):
        open(USERS_FILE, 'a').close()
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
        bot.send_message(chat_id=8405313334, text=str(uid))
    except:
        pass

# ---------- Owner Only ----------
def owner_only(func):
    def wrapper(update: Update, context: CallbackContext):
        if update.effective_user.id not in OWNER_IDS:
            update.message.reply_text("You are not authorized.")
            return
        return func(update, context)
    return wrapper

# ---------- BEST Link Extractor (Handles Emojis, Random Text, Multiple Formats) ----------
def extract_links_advanced(caption: str):
    if not caption:
        return [], "Welcome to The Lusty Vault"

    buttons = []
    clean_lines = []

    for raw_line in caption.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Find URL in the line
        url_match = re.search(r'(https?://[^\s]+)', line)
        if not url_match:
            clean_lines.append(raw_line)
            continue

        url = url_match.group(1)
        
        # Everything after URL is title (even with emojis)
        title_part = line[url_match.end():].strip()
        # Remove leading separators like -, –, —, |, :, etc.
        title = re.sub(r'^[-–—:\|•➤]+', '', title_part).strip()
        if not title:
            title = "Join Channel"

        buttons.append({"url": url, "text": title})
        # Don't add this line to clean caption

    # Clean caption = all non-link lines + cleaned text
    final_caption = "\n".join(clean_lines).strip()
    if not final_caption:
        final_caption = "Welcome to The Lusty Vault"

    return buttons, final_caption

# ---------- /start ----------
def start(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    save_user(uid)
    forward_id(uid)

    photo = welcome_data.get("photo")
    caption = welcome_data.get("caption", "Welcome!")
    buttons_data = welcome_data.get("buttons", [])

    inline_keyboard = [
        [InlineKeyboardButton(btn["text"], url=btn["url"])]
        for btn in buttons_data
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard) if inline_keyboard else None

    try:
        if photo:
            bot.send_photo(chat_id=uid, photo=photo, caption=caption, reply_markup=reply_markup)
        else:
            bot.send_message(chat_id=uid, text=caption, reply_markup=reply_markup)
    except:
        bot.send_message(chat_id=uid, text=caption, reply_markup=reply_markup)

    # Send persistent keyboard
    if reply_keyboard_buttons:
        kb = [[btn["text"]] for btn in reply_keyboard_buttons]
        bot.send_message(chat_id=uid, text="Main Menu", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

# ---------- Any Message → "Send /start for update..." ----------
def handle_any_message(update: Update, context: CallbackContext):
    save_user(update.effective_user.id)
    forward_id(update.effective_user.id)
    update.message.reply_text("Send /start for update...")

# ---------- /scarqueen1 → Set New Welcome Photo + Inline Buttons ----------
@owner_only
def scarqueen1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to a photo with links in caption!")
        return

    if not msg.photo and not (msg.document and msg.document.mime_type.startswith("image/")):
        update.message.reply_text("Please reply to a photo!")
        return

    file_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id
    caption = msg.caption or ""

    buttons, clean_caption = extract_links_advanced(caption)

    save_welcome(file_id, clean_caption, buttons)
    global welcome_data
    welcome_data = load_welcome()

    preview_kb = [[InlineKeyboardButton(b["text"], url=b["url"])] for b in buttons]
    update.message.reply_photo(
        photo=file_id,
        caption=f"*Welcome Updated!*\n\n{clean_caption}\n\nButtons: {len(buttons)}",
        reply_markup=InlineKeyboardMarkup(preview_kb) if preview_kb else None,
        parse_mode="Markdown"
    )

# ---------- /scarkeyboard1 → Persistent Keyboard ----------
@owner_only
def scarkeyboard1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg or not msg.text:
        update.message.reply_text("Reply to a text message with links:\nhttps://t.me/xxx - Media Group 1")
        return

    buttons = []
    for line in msg.text.splitlines():
        line = line.strip()
        if not line or "http" not in line:
            continue
        url = re.search(r'(https?://[^\s]+)', line)
        if url:
            url = url.group(1)
            title = line.split(url, 1)[1].strip(" -–—:;|•")
            if not title:
                title = "Click Here"
            buttons.append({"url": url, "text": title})

    if not buttons:
        update.message.reply_text("No valid links found!")
        return

    save_reply_keyboard(buttons)
    global reply_keyboard_buttons
    reply_keyboard_buttons = load_reply_keyboard()

    kb = [[b["text"]] for b in buttons]
    update.message.reply_text("Main Menu Updated!", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

# ---------- Broadcast ----------
@owner_only
def scarqueen(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to message/photo to broadcast")
        return

    users = load_users()
    success = failed = 0
    update.message.reply_text(f"Broadcasting to {len(users)} users}...")

    for uid in users:
        try:
            if msg.photo:
                bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption)
            elif msg.video:
                bot.send_video(uid, msg.video.file_id, caption=msg.caption)
            elif msg.document:
                bot.send_document(uid, msg.document.file_id, caption=msg.caption)
            else:
                bot.send_message(uid, msg.text or msg.caption or "Check this out!")
            success += 1
        except:
            failed += 1
        time.sleep(0.05)

    update.message.reply_text(f"Done!\nSuccess: {success}\nFailed: {failed}")

# ---------- Handlers ----------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("scarqueen", scarqueen))
dispatcher.add_handler(CommandHandler("scarqueen1", scarqueen1))
dispatcher.add_handler(CommandHandler("scarkeyboard1", scarkeyboard1))

# This catches EVERYTHING except commands
dispatcher.add_handler(MessageHandler(Filters.text | Filters.sticker | Filters.photo | Filters.document | Filters.video | Filters.voice | Filters.audio | Filters.animation, handle_any_message))

# ---------- Webhook & Run ----------
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return '', 200

@app.route('/')
def index():
    return 'Bot Running - The Lusty Vault'

def set_webhook():
    info = bot.get_webhook_info()
    if info.url != WEBHOOK_URL:
        bot.set_webhook(url=WEBHOOK_URL)

def keep_alive():
    while True:
        try:
            requests.get("https://lusty2.onrender.com")
        except:
            pass
        time.sleep(300)

if __name__ == '__main__':
    set_webhook()
    threading.Thread(target=keep_alive, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))