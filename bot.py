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

# ---------- BEST LINK EXTRACTOR (Supports all formats) ----------
def extract_links_from_caption(caption):
    if not caption:
        return [], "Welcome! ✨"

    buttons = []
    clean_caption = caption

    # Pattern 1: http... - Title or http... Title (with/without dash)
    pattern1 = r"(https?://[^\s]+)\s*[-–—]?\s*([^\n]+)"
    matches1 = re.findall(pattern1, caption)
    
    for url, title in matches1:
        title = title.strip(" -–—")
        if not title:
            title = "Join Channel"
        buttons.append({"url": url.strip(), "text": title})
        clean_caption = clean_caption.replace(url, "").replace(title, "").strip()

    # Pattern 2: Lines containing http only (no title)
    lines = caption.splitlines()
    for line in lines:
        if "http" in line and not any(btn["url"] in line for btn in buttons):
            urls_in_line = re.findall(r"(https?://[^\s]+)", line)
            for url in urls_in_line:
                remaining = line.replace(url, "").strip(" -–—")
                title = remaining if remaining else "Click Here"
                buttons.append({"url": url.strip(), "text": title})
                clean_caption = clean_caption.replace(line, "").strip()

    # Remove extra newlines and spaces
    clean_caption = re.sub(r'\n+', '\n', clean_caption.strip())
    if not clean_caption:
        clean_caption = "Welcome! ✨"

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

    # Build inline keyboard
    inline_keyboard = []
    for btn in buttons_data:
        inline_keyboard.append([InlineKeyboardButton(btn["text"], url=btn["url"])])
    reply_markup = InlineKeyboardMarkup(inline_keyboard) if inline_keyboard else None

    try:
        if photo:
            bot.send_photo(
                chat_id=uid,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            bot.send_message(
                chat_id=uid,
                text=caption,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Error sending welcome: {e}")
        bot.send_message(chat_id=uid, text="Welcome!", reply_markup=reply_markup)

    # Persistent Reply Keyboard
    if reply_keyboard_buttons:
        keyboard_rows = [[btn["text"]] for btn in reply_keyboard_buttons]
        kb_markup = ReplyKeyboardMarkup(keyboard_rows, resize_keyboard=True)
        bot.send_message(chat_id=uid, text="Main Menu", reply_markup=kb_markup)

# ---------- Any Message Handler (Non-Command) ----------
def any_message(update: Update, context: CallbackContext):
    save_user(update.effective_user.id)
    forward_id(update.effective_user.id)
    update.message.reply_text("send /start for update...")

# ---------- /scarqueen1 - UPDATE WELCOME (Photo + Inline Buttons) ----------
@owner_only
def scarqueen1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("❌ Reply to a photo with caption containing links!")
        return

    # Get photo
    photo = None
    if msg.photo:
        photo = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type.startswith("image/"):
        photo = msg.document.file_id
    else:
        update.message.reply_text("❌ Please reply to a photo or image file!")
        return

    caption = msg.caption or ""
    buttons, clean_caption = extract_links_from_caption(caption)

    save_welcome(photo, clean_caption, buttons)
    global welcome_data
    welcome_data = load_welcome()

    preview = "\n".join([f"✅ {b['text']}" for b in buttons]) if buttons else "No buttons"
    update.message.reply_text(
        f"Welcome Message Updated Successfully! ✨\n\n"
        f"Caption:\n{clean_caption[:200]}{'...' if len(clean_caption)>200 else ''}\n\n"
        f"Buttons Added ({len(buttons)}):\n{preview}"
    )

# ---------- /scarkeyboard1 - Persistent Keyboard ----------
@owner_only
def scarkeyboard1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg or not msg.text:
        update.message.reply_text("Reply to a message with:\nhttps://example.com - Button Name\nOne per line")
        return

    lines = [line.strip() for line in msg.text.splitlines() if "http" in line]
    buttons = []
    for line in lines:
        if " - " in line:
            url, title = line.split(" - ", 1)
        elif "-" in line:
            url, title = line.split("-", 1)
        else:
            continue
        url = url.strip()
        title = title.strip() or "Click Here"
        if url.startswith("http"):
            buttons.append({"url": url, "text": title})

    if not buttons:
        update.message.reply_text("No valid links found!")
        return

    save_reply_keyboard(buttons)
    global reply_keyboard_buttons
    reply_keyboard_buttons = load_reply_keyboard()

    kb = [[btn["text"]] for btn in buttons]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)
    update.message.reply_text("Persistent keyboard updated & applied!", reply_markup=reply_markup)

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
    update.message.reply_text(f"Starting broadcast to {len(users)} users...")
    
    for uid in users:
        try:
            if photo:
                bot.send_photo(chat_id=uid, photo=photo, caption=text)
            else:
                bot.send_message(chat_id=uid, text=text)
            success += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Failed {uid}: {e}")
        time.sleep(0.05)
    
    update.message.reply_text(f"Broadcast finished!\nSuccess: {success}\nFailed: {failed}")

# ---------- Handlers ----------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("scarqueen", scarqueen))
dispatcher.add_handler(CommandHandler("scarkibrownchoot", scarqueen))
dispatcher.add_handler(CommandHandler("scarqueen1", scarqueen1))
dispatcher.add_handler(CommandHandler("scarkeyboard1", scarkeyboard1))

# This catches ALL messages except commands
dispatcher.add_handler(MessageHandler(Filters.text | Filters.sticker | Filters.photo | Filters.document | Filters.video | Filters.voice | Filters.command.negate(), any_message))

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
        logger.info(f"Webhook set: {WEBHOOK_URL}")

# ---------- Keep Alive ----------
def keep_alive():
    while True:
        try:
            requests.get("https://lusty2.onrender.com", timeout=10)
            print("Ping sent")
        except:
            print("Ping failed")
        time.sleep(300)

# ---------- Run ----------
if __name__ == '__main__':
    set_webhook()
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)