import os
import json
import logging
import threading
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

# --------------------- CONFIG ---------------------
TOKEN = os.getenv("BOT_TOKEN")          # MUST be set in Render
OWNER_ID = 8405313334                   # (optional - not used for global update)
USERS_FILE = "users.txt"
WELCOME_FILE = "welcome.json"           # stores global + per-user
# --------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# ---------- persistent data ----------
user_welcome = {}          # per-user (optional fallback)
global_welcome = None      # {"text": str, "photo": file_id or None}
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
    global user_welcome, global_welcome
    if os.path.exists(WELCOME_FILE):
        try:
            with open(WELCOME_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                per_user = data.get("per_user", {})
                for uid, val in per_user.items():
                    if isinstance(val, list):
                        per_user[uid] = {"text": val[0], "photo": val[1]}
                user_welcome = {int(k): v for k, v in per_user.items()}
                global_welcome = data.get("global")
            logger.info("Welcome data loaded.")
        except Exception as e:
            logger.error(f"Failed to load welcome file: {e}")
    else:
        user_welcome = {}
        global_welcome = None


def save_welcome():
    with lock:
        try:
            data = {
                "per_user": user_welcome,
                "global": global_welcome
            }
            with open(WELCOME_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Welcome data saved.")
        except Exception as e:
            logger.error(f"Failed to save welcome file: {e}")


# Load on startup
load_welcome()


# ---------- SEND WELCOME ----------
def send_welcome(uid: int):
    if global_welcome:
        try:
            if global_welcome.get("photo"):
                bot.send_photo(chat_id=uid, photo=global_welcome["photo"], caption=global_welcome.get("text", ""))
            else:
                bot.send_message(chat_id=uid, text=global_welcome.get("text", "Welcome!"))
        except Exception as e:
            logger.warning(f"Global send failed for {uid}: {e}")
            bot.send_message(chat_id=uid, text=global_welcome.get("text", "Welcome!"))
        return

    if uid in user_welcome:
        data = user_welcome[uid]
        try:
            if data.get("photo"):
                bot.send_photo(chat_id=uid, photo=data["photo"], caption=data.get("text", ""))
            else:
                bot.send_message(chat_id=uid, text=data.get("text", "Welcome!"))
        except Exception as e:
            logger.warning(f"Per-user send failed for {uid}: {e}")
        return

    bot.send_message(chat_id=uid, text="Welcome to the lusty vault \n join backup")


# ---------- HANDLERS ----------
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    save_user(uid)
    forward_id(uid)
    send_welcome(uid)


def any_message(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    save_user(uid)
    forward_id(uid)
    update.message.reply_text("Send /start for update...")


def scarkibrownchoot(update: Update, context: CallbackContext):
    """ANYONE can set GLOBAL welcome by replying with /scarkibrownchoot"""
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to a message (text/photo) with /scarkibrownchoot to set global welcome.")
        return

    text = (msg.caption or msg.text or "").strip()
    photo = None

    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith('image/'):
        photo = msg.document.file_id

    global global_welcome
    global_welcome = {"text": text, "photo": photo}
    save_welcome()

    # Optional: clear per-user welcomes so global is the only one
    user_welcome.clear()
    save_welcome()

    update.message.reply_text("Global welcome updated! Everyone will now get this on /start.")


def scarhellboykelaudepr(update: Update, context: CallbackContext):
    """BROADCAST to all users"""
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply with /scarhellboykelaudepr to broadcast")
        return

    users = load_users()
    if not users:
        update.message.reply_text("No users.")
        return

    text = (msg.caption or msg.text or "").strip()
    photo = None

    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith('image/'):
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
            logger.warning(f"Broadcast failed to {uid}: {e}")

    update.message.reply_text(f"Sent to {success}/{len(users)} users.")


# ---------- REGISTER ----------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("scarkibrownchoot", scarkibrownchoot))  # Now global
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
        logger.info("Webhook already correct.")


# ---------- RUN ----------
if __name__ == '__main__':
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)