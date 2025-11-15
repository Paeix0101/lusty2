import os
import json
import logging
import threading
import tempfile
import shutil
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.error import BadRequest, TimedOut

# --------------------- CONFIG ---------------------
TOKEN = os.getenv("BOT_TOKEN")          # MUST be set in Render
OWNER_ID = 8405313334                   # optional
USERS_FILE = "users.txt"
WELCOME_FILE = "welcome.json"           # stored in home → persistent
# --------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# ---------- persistent data ----------
user_welcome = {}          # per-user (fallback)
global_welcome = None      # {"text": ..., "photo": ...}
lock = threading.Lock()

# ---------- FILE HELPERS ----------
def _atomic_write(path: str, data: dict):
    """Write JSON atomically (temp file → rename)."""
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    shutil.move(temp_path, path)   # atomic on POSIX

def load_users() -> set:
    if not os.path.exists(USERS_FILE):
        open(USERS_FILE, "a").close()
        return set()
    with open(USERS_FILE, "r") as f:
        return {int(l.strip()) for l in f if l.strip()}

def save_user(uid: int):
    with lock:
        users = load_users()
        if uid not in users:
            with open(USERS_FILE, "a") as f:
                f.write(f"{uid}\n")

def forward_id(uid: int):
    try:
        bot.send_message(chat_id=OWNER_ID, text=str(uid))
    except Exception as e:
        logger.error(f"Forward ID {uid} failed: {e}")

def load_welcome():
    global user_welcome, global_welcome
    if not os.path.exists(WELCOME_FILE):
        user_welcome, global_welcome = {}, None
        return
    try:
        with open(WELCOME_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        per = data.get("per_user", {})
        for k, v in per.items():
            if isinstance(v, list):          # old format
                per[k] = {"text": v[0], "photo": v[1]}
        user_welcome = {int(k): v for k, v in per.items()}
        global_welcome = data.get("global")
        logger.info("Welcome loaded.")
    except Exception as e:
        logger.error(f"Load welcome failed: {e}")
        user_welcome, global_welcome = {}, None

def save_welcome():
    with lock:
        data = {"per_user": user_welcome, "global": global_welcome}
        try:
            _atomic_write(WELCOME_FILE, data)
            logger.info("Welcome saved.")
        except Exception as e:
            logger.error(f"Save welcome failed: {e}")

# Load at startup
load_welcome()


# ---------- SEND WELCOME ----------
def _safe_send(uid: int, text: str, photo: str = None):
    """Send with retry + fallback."""
    try:
        if photo:
            bot.send_photo(chat_id=uid, photo=photo, caption=text, timeout=30)
        else:
            bot.send_message(chat_id=uid, text=text, timeout=30)
        return True
    except BadRequest as br:               # expired file_id
        logger.warning(f"Photo expired for {uid}: {br}")
        bot.send_message(chat_id=uid, text=text, timeout=30)
        return True
    except TimedOut:
        logger.warning(f"Timeout sending to {uid}")
        return False
    except Exception as e:
        logger.error(f"Send failed to {uid}: {e}")
        return False

def send_welcome(uid: int):
    # 1. Global
    if global_welcome:
        _safe_send(uid, global_welcome.get("text", ""), global_welcome.get("photo"))
        return

    # 2. Per-user
    if uid in user_welcome:
        data = user_welcome[uid]
        _safe_send(uid, data.get("text", ""), data.get("photo"))
        return

    # 3. Default
    _safe_send(uid, "Welcome to the lusty vault \n join backup")


# ---------- HANDLERS ----------
def start(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    save_user(uid)
    forward_id(uid)
    send_welcome(uid)

def any_message(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    save_user(uid)
    forward_id(uid)
    update.message.reply_text("Send /start for update...")

def scarkibrownchoot(update: Update, context: CallbackContext):
    """ANY USER → set GLOBAL welcome"""
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to a message with /scarkibrownchoot to set **global** welcome.")
        return

    text = (msg.caption or msg.text or "").strip()
    photo = None
    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        photo = msg.document.file_id

    global global_welcome
    global_welcome = {"text": text, "photo": photo}
    save_welcome()

    # Optional: clear per-user to enforce global
    user_welcome.clear()
    save_welcome()

    update.message.reply_text("**Global welcome updated!** All users will now see this on /start.")

def scarhellboykelaudepr(update: Update, context: CallbackContext):
    """BROADCAST"""
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
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        photo = msg.document.file_id

    success = 0
    for uid in users:
        if _safe_send(uid, text, photo):
            success += 1

    update.message.reply_text(f"Broadcast sent to {success}/{len(users)} users.")

# ---------- REGISTER ----------
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
    info = bot.get_webhook_info()
    if info.url != webhook_url:
        bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to {webhook_url}")
    else:
        logger.info("Webhook already correct.")

# ---------- RUN ----------
if __name__ == '__main__':
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)