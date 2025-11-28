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

# ---------- Load & Save Welcome ----------
def load_welcome():
    if not os.path.exists(WELCOME_FILE):
        return {"photo": None, "caption": "Welcome!", "buttons": []}
    try:
        with open(WELCOME_FILE, "r") as f:
            return json.load(f)
    except:
        return {"photo": None, "caption": "Welcome!", "buttons": []}

def save_welcome(photo_id, caption, buttons):
    with open(WELCOME_FILE, "w") as f:
        json.dump({"photo": photo_id, "caption": caption, "buttons": buttons}, f)

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
    except Exception as e:
        logger.error(f"Failed to forward ID {uid}: {e}")

# ---------- Owner Only ----------
def owner_only(func):
    def wrapper(update: Update, context: CallbackContext):
        if update.effective_user.id not in OWNER_IDS:
            update.message.reply_text("You are not authorized.")
            return
        return func(update, context)
    return wrapper

# ---------- Extract Links ----------
def extract_links_from_caption(caption):
    if not caption:
        return [], "Welcome!"
    pattern = r"(https?://[^\s]+)\s*-?\s*([^\n]+)"
    matches = re.findall(pattern, caption)
    buttons = []
    clean_caption = caption

    for url, title in matches:
        title = title.strip(" -")
        if not title:
            title = "Open Link"
        buttons.append({"url": url.strip(), "text": title})
        clean_caption = re.sub(re.escape(url) + r".*" + re.escape(title), "", clean_caption, count=1).strip()

    if not buttons:
        for line in caption.splitlines():
            if "http" in line:
                parts = line.split()
                url = next((p for p in parts if p.startswith("http")), None)
                if url:
                    title = " ".join([p for p in parts if p != url]) or "Join"
                    buttons.append({"url": url, "text": title})
                    clean_caption = clean_caption.replace(line, "").strip()
    return buttons, clean_caption or "Welcome!"

# ---------- /start ----------
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    save_user(uid)
    forward_id(uid)

    # Inline buttons from welcome
    inline_kb = [[InlineKeyboardButton(b["text"], url=b["url"]) for b in welcome_data["buttons"]]]
    inline_markup = InlineKeyboardMarkup(inline_kb) if welcome_data["buttons"] else None

    try:
        if welcome_data["photo"]:
            bot.send_photo(
                chat_id=uid,
                photo=welcome_data["photo"],
                caption=welcome_data["caption"],
                reply_markup=inline_markup
            )
        else:
            bot.send_message(chat_id=uid, text=welcome_data["caption"], reply_markup=inline_markup)
    except:
        bot.send_message(chat_id=uid, text="Welcome! Use the buttons below", reply_markup=inline_markup)

    # FIXED: Bottom persistent keyboard (THIS WAS THE BUG!)
    if reply_keyboard_buttons:
        # Correct way: one button per row, or multiple per row
        kb_rows = [[btn["text"]] for btn in reply_keyboard_buttons]  # ← Fixed line
        # If you want 2 buttons per row, use this instead:
        # kb_rows = [reply_keyboard_buttons[i:i+2] for i in range(0, len(reply_keyboard_buttons), 2)]
        reply_markup = ReplyKeyboardMarkup(kb_rows, resize_keyboard=True)
        bot.send_message(chat_id=uid, text="Your Menu:", reply_markup=reply_markup)

# ---------- Any Message ----------
def any_message(update: Update, context: CallbackContext):
    save_user(update.effective_user.id)
    forward_id(update.effective_user.id)
    update.message.reply_text("Send /start to see the menu.")

# ---------- /scarqueen1 ----------
@owner_only
def scarqueen1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg or not (msg.photo or (msg.document and msg.document.mime_type.startswith("image/"))):
        update.message.reply_text("Reply to a photo with links in caption!")
        return

    photo = msg.photo[-1].file_id if msg.photo else msg.document.file_id
    caption = msg.caption or ""
    buttons, clean_caption = extract_links_from_caption(caption)

    save_welcome(photo, clean_caption, buttons)
    global welcome_data
    welcome_data = load_welcome()

    update.message.reply_text(f"Welcome updated! {len(buttons)} inline buttons set.")

# ---------- /scarkeyboard1 ----------
@owner_only
def scarkeyboard1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg or not msg.text:
        update.message.reply_text("Reply to text with:\nhttps://link - Button Name")
        return

    lines = [l.strip() for l in msg.text.splitlines() if "http" in l or "-" in l]
    buttons = []
    for line in lines:
        if " - " in line:
            url, title = line.split(" - ", 1)
        elif "-" in line:
            url, title = line.split("-", 1)
        else:
            continue
        url = url.strip()
        title = title.strip() or "Link"
        if url.startswith("http"):
            buttons.append({"url": url, "text": title})

    if not buttons:
        update.message.reply_text("No valid links found!")
        return

    save_reply_keyboard(buttons)
    global reply_keyboard_buttons
    reply_keyboard_buttons = buttons

    kb = [[b["text"]] for b in buttons]
    update.message.reply_text("Bottom keyboard updated!", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

# ---------- Broadcast ----------
@owner_only
def scarqueen(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to message/photo to broadcast!")
        return

    users = load_users()
    success = failed = 0
    text = msg.caption or msg.text or ""
    photo = msg.photo[-1].file_id if msg.photo else None

    update.message.reply_text(f"Broadcasting to {len(users)} users...")

    for uid in users:
        try:
            if photo:
                bot.send_photo(uid, photo, caption=text)
            else:
                bot.send_message(uid, text)
            success += 1
        except:
            failed += 1
        time.sleep(0.05)

    update.message.reply_text(f"Broadcast Done!\nSuccess: {success}\nFailed: {failed}")

# ---------- Handlers ----------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("scarqueen1", scarqueen1))
dispatcher.add_handler(CommandHandler("scarkeyboard1", scarkeykeyboard1))
dispatcher.add_handler(CommandHandler("scarqueen", scarqueen))
dispatcher.add_handler(MessageHandler(Filters.all & ~Filters.command, any_message))

# ---------- Webhook ----------
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return '', 200

@app.route('/')
def index():
    return 'Bot is running!'

def set_webhook():
    info = bot.get_webhook_info()
    if info.url != WEBHOOK_URL:
        bot.set_webhook(url=WEBHOOK_URL)
        logger.info("Webhook set!")

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
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))