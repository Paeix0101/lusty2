import os
import json
import logging
import threading
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

# --------------------- CONFIG ---------------------
TOKEN = os.getenv("BOT_TOKEN")          # MUST be set in Render
OWNER_ID = 8405313334                   # your Telegram ID
USERS_FILE = "users.txt"
WELCOME_FILE = "welcome.json"           # NEW: persistent welcome storage
# --------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# ---------- persistent data ----------
user_welcome = {}          # {user_id: {"text": str, "photo": file_id or None}}
lock = threading.Lock()


# ---------- FILE HELPERS ----------
def load_users() -> set:
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


def load_welcome():
    """Load welcome dict from JSON file."""
    global user_welcome
    if os.path.exists(WELCOME_FILE):
        try:
            with open(WELCOME_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Convert old tuple format if exists
                for uid, val in data.items():
                    if isinstance(val, list):  # old format [text, photo]
                        data[uid] = {"text": val[0], "photo": val[1]}
                user_welcome = {int(k): v for k, v in data.items()}
            logger.info("Welcome messages loaded.")
        except Exception as e:
            logger.error(f"Failed to load welcome file: {e}")
    else:
        user_welcome = {}


def save_welcome():
    """Save welcome dict to JSON file."""
    with lock:
        try:
            with open(WELCOME_FILE, 'w', encoding='utf-8') as f:
                json.dump(user_welcome, f, ensure_ascii=False, indent=2)
            logger.info("Welcome messages saved.")
        except Exception as e:
            logger.error(f"Failed to save welcome file: {e}")


# Load on startup
load_welcome()


# ---------- HANDLERS ----------
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    save_user(uid)
    forward_id(uid)

    # Default welcome if not customized
    if uid not in user_welcome:
        default_text = "Welcome to the lusty vault \n join backup"
        bot.send_message(chat_id=uid, text=default_text)
        return

    # Send saved custom welcome
    data = user_welcome[uid]
    text = data.get("text", "")
    photo = data.get("photo")

    try:
        if photo:
            bot.send_photo(chat_id=uid, photo=photo, caption=text)
        else:
            bot.send_message(chat_id=uid, text=text)
    except Exception as e:
        logger.warning(f"Failed to send welcome to {uid}: {e}")
        bot.send_message(chat_id=uid, text=text or "Welcome!")


def any_message(update: Update, context: CallbackContext):
    """Auto-reply to any non-command message"""
    user = update.effective_user
    uid = user.id
    save_user(uid)
    forward_id(uid)
    update.message.reply_text("Send /start for update...")


def scarkibrownchoot(update: Update, context: CallbackContext):
    """SET permanent welcome: reply to any message with /scarkibrownchoot"""
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("❗ Reply to a message (text/photo/doc) with /scarkibrownchoot")
        return

    uid = update.effective_user.id

    text = (msg.caption or msg.text or "").strip()
    photo = None

    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type.startswith('image/'):
        photo = msg.document.file_id

    # Save permanently
    user_welcome[uid] = {"text": text, "photo": photo}
    save_welcome()

    update.message.reply_text("✅ New welcome message saved permanently!")


def scarhellboykelaudepr(update: Update, context: CallbackContext):
    """BROADCAST to all saved users"""
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("❗ Reply to a message with /scarhellboykelaudepr to broadcast")
        return

    users = load_users()
    if not users:
        update.message.reply_text("No users to broadcast to.")
        return

    text = (msg.caption or msg.text or "").strip()
    photo = None

    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type.startswith('image/'):
        photo = msg.document.file_id

    success = 0
    for uid in users:
        try:
            if photo:
                bot.send_photo(chat_id=uid, photo=photo, caption=text)
            else:
                bot.send_message(chat_id=uid, text=text or " ")
            success += 1
        except Exception as e:
            logger.warning(f"Failed to send to {uid}: {e}")

    update.message.reply_text(f"Broadcast sent to {success}/{len(users)} users.")


# ---------- REGISTER HANDLERS ----------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("scarkibrownchoot", scarkibrownchoot))
dispatcher.add_handler(CommandHandler("scarhellboykelaudepr", scarhellboykelaudepr))
dispatcher.add_handler(MessageHandler(Filters.all & ~Filters.command, any_message))


# ---------- WEBHOOK ----------
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    if update:
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
    else:
        logger.info("Webhook already set.")


# ---------- RUN ----------
if __name__ == '__main__':
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)