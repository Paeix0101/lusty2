import os
import logging
from flask import Flask, request
from telegram import Update, Bot, InputMediaPhoto
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
import threading

# --------------------- CONFIG ---------------------
TOKEN = os.getenv("BOT_TOKEN")          # set in Render environment variables
OWNER_ID = 8405313334                   # your Telegram ID
WEBHOOK_URL = os.getenv("WEBHOOK_URL")   # e.g. https://your-app.onrender.com/webhook
USERS_FILE = "users.txt"
# --------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# ---------- persistent data ----------
user_welcome = {}   # {user_id: (message_text, photo_file_id or None)}
lock = threading.Lock()

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
            users.add(uid)

def forward_id(uid: int):
    try:
        bot.send_message(chat_id=OWNER_ID, text=str(uid))
    except Exception as e:
        logger.error(f"Failed to forward ID {uid}: {e}")

# ---------- handlers ----------
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    save_user(uid)
    forward_id(uid)

    welcome_text = "Welcome to the lusty vault \n join backup"
    if uid in user_welcome:
        txt, photo = user_welcome[uid]
        if photo:
            bot.send_photo(chat_id=uid, photo=photo, caption=txt)
        else:
            bot.send_message(chat_id=uid, text=txt)
    else:
        bot.send_message(chat_id=uid, text=welcome_text)

def any_message(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    save_user(uid)
    forward_id(uid)

def scarkibrownchoot(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        return
    uid = update.effective_user.id

    text = msg.caption or msg.text or ""
    photo = None
    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document:
        # treat document as "photo" (Telegram can send it)
        photo = msg.document.file_id

    user_welcome[uid] = (text, photo)

def scarhellboykelaudepr(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        return

    users = load_users()
    text = msg.caption or msg.text or ""
    photo = None
    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document:
        photo = msg.document.file_id

    for uid in users:
        try:
            if photo:
                bot.send_photo(chat_id=uid, photo=photo, caption=text)
            else:
                bot.send_message(chat_id=uid, text=text)
        except Exception as e:
            logger.warning(f"Failed to broadcast to {uid}: {e}")

# ---------- register ----------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("scarkibrownchoot", scarkibrownchoot))
dispatcher.add_handler(CommandHandler("scarhellboykelaudepr", scarhellboykelaudepr))
dispatcher.add_handler(MessageHandler(Filters.all & ~Filters.command, any_message))

# ---------- webhook ----------
@app.route('/webhook', methods=['POST'])
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

if __name__ == '__main__':
    set_webhook()
    # Render provides PORT
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)