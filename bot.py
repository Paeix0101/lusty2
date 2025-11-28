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
WELCOME_FILE = "welcome.json"           # For /start (photo + inline buttons)
KEYBOARD_FILE = "keyboard.json"         # For persistent reply keyboard

WEBHOOK_URL = f"https://lusty2.onrender.com/{TOKEN}"
# --------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

lock = threading.Lock()

# ---------- Load & Save Welcome (Photo + Inline Buttons) ----------
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

# ---------- Load & Save Reply Keyboard ----------
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

# ---------- Persistent Users ----------
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
    except Exception as e:
        logger.error(f"Failed to forward ID {uid}: {e}")

# ---------- Owner Only Decorator ----------
def owner_only(func):
    def wrapper(update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        if user_id not in OWNER_IDS:
            update.message.reply_text("You are not authorized.")
            return
        return func(update, context)
    return wrapper

# ---------- Extract Links & Titles from Caption ----------
def extract_links_from_caption(caption):
    if not caption:
        return []
    pattern = r"(https?://[^\s]+)\s*-?\s*([^\n]+)"
    matches = re.findall(pattern, caption)
    buttons = []
    clean_caption = caption
    for url, title in matches:
        title = title.strip().strip("-").strip()
        if not title:
            title = "Open Link"
        buttons.append({"url": url.strip(), "text": title})
        clean_caption = clean_caption.replace(f"{url} - {title}", "").replace(f"{url}-{title}", "").strip()
    # Fallback: if no -, just take first word as title
    if not buttons:
        lines = [line.strip() for line in caption.splitlines() if "http" in line]
        for line in lines:
            parts = line.split()
            url = next((p for p in parts if p.startswith("http")), None)
            if url:
                title = " ".join([p for p in parts if p != url]) or "Join Here"
                buttons.append({"url": url, "text": title})
                clean_caption = clean_caption.replace(line, "").strip()
    return buttons, clean_caption or "Welcome!"

# ---------- /start - Send Welcome with Inline Buttons ----------
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    save_user(uid)
    forward_id(uid)

    photo = welcome_data["photo"]
    caption = welcome_data["caption"]
    buttons_data = welcome_data["buttons"]

    keyboard = []
    for btn in buttons_data:
        keyboard.append([InlineKeyboardButton(btn["text"], url=btn["url"])])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    try:
        if photo:
            bot.send_photo(chat_id=uid, photo=photo, caption=caption, reply_markup=reply_markup)
        else:
            bot.send_message(chat_id=uid, text=caption or "Welcome!", reply_markup=reply_markup)
    except Exception as e:
        bot.send_message(chat_id=uid, text="Welcome! Use the buttons below 👇", reply_markup=reply_markup)

    # Also send persistent reply keyboard
    if reply_keyboard_buttons:
        kb = [btn["9940text"] for btn in reply_keyboard_buttons]
        keyboard = ReplyKeyboardMarkup([kb], resize_keyboard=True)
        bot.send_message(chat_id=uid, text="Your menu:", reply_markup=keyboard)

# ---------- Any Message Handler ----------
def any_message(update: Update, context: CallbackContext):
    user = update.effective_user
    save_user(user.id)
    forward_id(user.id)
    update.message.reply_text("Send /start to see the menu.")

# ---------- /scarqueen1 - Set Welcome Photo + Inline Buttons ----------
@owner_only
def scarqueen1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to a photo with caption containing:\nlink - title")
        return

    photo = None
    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type.startswith("image/"):
        photo = msg.document.file_id
    else:
        update.message.reply_text("Please reply to a photo.")
        return

    caption = msg.caption or ""
    buttons, clean_caption = extract_links_from_caption(caption)

    save_welcome(photo, clean_caption, buttons)
    global welcome_data
    welcome_data = load_welcome()

    update.message.reply_text(f"Welcome updated!\nButtons: {len(buttons)}\nNew caption: {clean_caption}")

# ---------- /scarkeyboard1 - Set Persistent Reply Keyboard ----------
@owner_only
def scarkeyboard1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg or not msg.text:
        update.message.reply_text("Reply to a text message with:\nlink1 - Title 1\nlink2 - Title 2")
        return

    text = msg.text
    lines = [line.strip() for line in text.splitlines() if "-" in line or "http" in line]
    buttons = []

    for line in lines:
        if " - " in line:
            url, title = line.split(" - ", 1)
        elif "-" in line:
            url, title = line.split("-", 1)
        else:
            continue
        url = url.strip()
        title = title.strip()
        if not title:
            title = "Click Here"
        if url.startswith("http"):
            buttons.append({"url": url, "text": title})

    if not buttons:
        update.message.reply_text("No valid 'link - title' found!")
        return

    save_reply_keyboard(buttons)
    global reply_keyboard_buttons
    reply_keyboard_buttons = load_reply_keyboard()

    kb = [[btn["text"]] for btn in buttons]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)
    update.message.reply_text("Persistent keyboard updated!", reply_markup=reply_markup)

# ---------- Broadcast (Old scarqueen) ----------
@owner_only
def scarqueen(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to a message/photo to broadcast using /scarqueen")
        return

    text = (msg.caption or msg.text or "").strip()
    photo = None
    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        photo = msg.document.file_id

    users = load_users()
    success = failed = 0

    update.message.reply_text(f"Broadcasting to {len(users)} users...")

    for uid in users:
        try:
            if photo:
                bot.send_photo(chat_id=uid, photo=photo, caption=text)
            else:
                bot.send_message(chat_id=uid, text=text)
            success += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Failed to send to {uid}: {e}")

        time.sleep(0.05)  # Avoid flood

    update.message.reply_text(f"Broadcast Done!\nSuccess: {success}\nFailed: {failed}")

# ---------- Register Handlers ----------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("scarkibrownchoot", scarqueen))  # old broadcast
dispatcher.add_handler(CommandHandler("scarqueen", scarqueen))
dispatcher.add_handler(CommandHandler("scarqueen1", scarqueen1))      # NEW: inline welcome
dispatcher.add_handler(CommandHandler("scarkeyboard1", scarkeyboard1))  # NEW: reply keyboard
dispatcher.add_handler(MessageHandler(Filters.all & ~Filters.command, any_message))

# ---------- Webhook ----------
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return '', 200

@app.route('/')
def index():
    return 'Bot is alive!'

def set_webhook():
    current = bot.get_webhook_info()
    if current.url != WEBHOOK_URL:
        bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook set to {WEBHOOK_URL}")

# ---------- Keep Alive ----------
def keep_alive():
    while True:
        try:
            requests.get("https://lusty2.onrender.com", timeout=10)
            print("Keep-alive ping sent.")
        except:
            print("Keep-alive failed.")
        time.sleep(300)

# ---------- Main ----------
if __name__ == '__main__':
    set_webhook()
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)