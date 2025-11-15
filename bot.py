import os
import json
import logging
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
import threading

# --------------------- CONFIG ---------------------
TOKEN = os.getenv("BOT_TOKEN")  # MUST be set in Render
OWNER_ID = 8405313334  # your Telegram ID
USERS_FILE = "users.txt"
WELCOME_FILE = "welcome.json"
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


welcome_data = load_welcome()   # load at startup


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
        bot.send_message(chat_id=OWNER_ID, text=str(uid))
    except Exception as e:
        logger.error(f"Failed to forward ID {uid}: {e}")


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


def scarkibrownchoot(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        return

    # Only OWNER can update welcome message permanently
    if update.effective_user.id != OWNER_ID:
        return

    text = msg.caption or msg.text or ""
    photo = None

    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document:
        photo = msg.document.file_id

    # Save permanently
    save_welcome(text, photo)

    # Update in RAM also
    global welcome_data
    welcome_data = load_welcome()

    update.message.reply_text("✅ Permanent welcome message updated!")


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
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return '', 200


@app.route('/')
def index():
    return 'Bot is alive!'


def set_webhook():
    webhook_url = f"https://lusty2.onrender.com/{TOKEN}"
    current = bot.get_webhook_info()
    if current.url != webhook_url:
        bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to {webhook_url}")


if __name__ == '__main__':
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
