import os
import json
import logging
import threading
import time
import requests

from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

# --------------------- CONFIG ---------------------
TOKEN = os.getenv("BOT_TOKEN")  # MUST be set in Render
OWNER_IDS = {8183414512, 6218772339, 8141547148, 7514171886}  # Only these can use admin commands
USERS_FILE = "users.txt"
WELCOME_FILE = "welcome.json"

WEBHOOK_URL = f"https://lusty2.onrender.com/{TOKEN}"
# --------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

lock = threading.Lock()

# ---------- load & save permanent welcome ----------
def load_welcome():
    if not os.path.exists(WELCOME_FILE):
        return {"text": "Welcome to the lusty vault \n join backup", "photo": None}

    try:
        with open(WELCOME_FILE, "r") as f:
            return json.load(f)
    except:
        return {"text": "Welcome to the lusty vault \n join backup", "photo": None}

def save_welcome(text, photo):
    data = {"text": text, "photo": photo}
    with open(WELCOME_FILE, "w") as f:
        json.dump(data, f)

welcome_data = load_welcome()

# ---------- persistent users ----------
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

# ---------- owner check decorator ----------
def owner_only(func):
    def wrapper(update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        if user_id not in OWNER_IDS:
            update.message.reply_text("❌ You are not authorized to use this command.")
            return
        return func(update, context)
    return wrapper

# ---------- handlers ----------
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    save_user(uid)
    forward_id(uid)

    text = welcome_data["text"]
    photo = welcome_data["photo"]

    if photo:
        bot.send_photo(chat_id=uid, photo=photo, caption=text)
    else:
        bot.send_message(chat_id=uid, text=text)

def any_message(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    save_user(uid)
    forward_id(uid)
    update.message.reply_text("Send /start for update...")

@owner_only
def scarkibrownchoot(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("⚠️ Please reply to a message/photo/document to set as new welcome.")
        return

    text = (msg.caption or msg.text or "").strip()
    photo = None
    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        photo = msg.document.file_id

    save_welcome(text, photo)
    global welcome_data
    welcome_data = load_welcome()
    update.message.reply_text("✅ Permanent welcome message updated successfully!")

# NEW COMMAND: /scarqueen (Broadcast to all users)
@owner_only
def scarqueen(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("⚠️ Reply to a message/photo to broadcast using /scarqueen")
        return

    text = (msg.caption or msg.text or "").strip()
    photo = None
    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        photo = msg.document.file_id

    users = load_users()
    success = 0
    failed = 0

    update.message.reply_text(f"🚀 Broadcasting to {len(users)} users using /scarqueen...")

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

    update.message.reply_text(f"✅ Broadcast completed!\nSuccess: {success}\nFailed: {failed}")

# ---------- register handlers ----------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("scarkibrownchoot", scarkibrownchoot))
dispatcher.add_handler(CommandHandler("scarqueen", scarqueen))  # ← NEW COMMAND
dispatcher.add_handler(MessageHandler(Filters.all & ~Filters.command, any_message))

# ---------- webhook ----------
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

# ---------- KEEP ALIVE ----------
def keep_alive():
    while True:
        try:
            requests.get("https://lusty2.onrender.com")
            print("🔄 Keep-alive ping sent.")
        except Exception as e:
            print(f"❌ Keep-alive failed: {e}")
        time.sleep(300)

# ---------- MAIN ----------
if __name__ == '__main__':
    set_webhook()
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)