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

# ---------- Load/Save Users ----------
def load_users():
    if not os.path.exists(USERS_FILE):
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
        bot.send_message(8405313334, text=str(uid))
    except:
        pass

# ---------- Welcome Data ----------
def load_welcome():
    if not os.path.exists(WELCOME_FILE):
        return {"photo": None, "caption": "Lusty flirt", "buttons": []}
    try:
        with open(WELCOME_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"photo": None, "caption": "Lusty flirt", "buttons": []}

def save_welcome(photo_id, caption, buttons):
    data = {"photo": photo_id, "caption": caption, "buttons": buttons}
    with open(WELCOME_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

welcome_data = load_welcome()

# ---------- Keyboard Buttons ----------
def load_keyboard():
    if not os.path.exists(KEYBOARD_FILE):
        return []
    try:
        with open(KEYBOARD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_keyboard(items):
    with open(KEYBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

keyboard_items = load_keyboard()

# ---------- Owner Only Decorator ----------
def owner_only(func):
    def wrapper(update: Update, context: CallbackContext):
        if update.effective_user.id not in OWNER_IDS:
            update.message.reply_text("Unauthorized.")
            return
        return func(update, context)
    return wrapper

# ---------- Extract Button from Message (for keyboard) ----------
def extract_button_from_message(message):
    text = (message.caption or message.text or "").strip()
    if not text:
        return None, None

    match = re.search(r"(https?://[^\s]+)\s*[-–—]?\s*([^\n]+)", text)
    if not match:
        return None, None

    url = match.group(1).strip()
    title = match.group(2).strip() or "Click Here"

    content = {
        "text": message.text,
        "photo": message.photo[-1].file_id if message.photo else None,
        "document": message.document.file_id if message.document else None,
        "video": message.video.file_id if message.video else None,
        "caption": message.caption
    }

    return {"title": title, "url": url, "content": content}, title

# ---------- /start ----------
def start(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    save_user(uid)
    forward_id(uid)

    photo = welcome_data.get("photo")
    caption = welcome_data.get("caption", "Lusty flirt")
    buttons = welcome_data.get("buttons", [])

    inline_kb = [[InlineKeyboardButton(btn["text"], url=btn["url"])] for btn in buttons]
    inline_markup = InlineKeyboardMarkup(inline_kb) if inline_kb else None

    try:
        if photo:
            bot.send_photo(uid, photo, caption=caption, reply_markup=inline_markup, parse_mode="HTML")
        else:
            bot.send_message(uid, text=caption, reply_markup=inline_markup, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        bot.send_message(uid, "Welcome! Use /start again.")

    # Send persistent keyboard
    if keyboard_items:
        kb = [[item["title"]] for item in keyboard_items]
        bot.send_message(uid, "Choose an option:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

# ---------- Handle Keyboard Button Click ----------
def handle_button_click(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    uid = update.effective_user.id
    save_user(uid)

    for item in keyboard_items:
        if item["title"] == text:
            content = item["content"]
            try:
                if content.get("photo"):
                    bot.send_photo(uid, content["photo"], caption=content.get("caption") or content.get("text"), parse_mode="HTML")
                elif content.get("video"):
                    bot.send_video(uid, content["video"], caption=content.get("caption"))
                elif content.get("document"):
                    bot.send_document(uid, content["document"], caption=content.get("caption"))
                elif content.get("text"):
                    bot.send_message(uid, content["text"], disable_web_page_preview=True, parse_mode="HTML")
            except:
                bot.send_message(uid, "Content expired or error.")
            return

# ---------- Dynamic Add Button Handlers ----------
def create_add_button_handler(position):
    @owner_only
    def add_button(update: Update, context: CallbackContext):
        global keyboard_items
        msg = update.message.reply_to_message
        if not msg:
            update.message.reply_text(f"Reply to a message/photo with link and title!\nExample:\nhttps://t.me/xxx - Premium Vault {position}")
            return

        button_data, title = extract_button_from_message(msg)
        if not button_data:
            update.message.reply_text("No valid link-title found! Use: https://link - Title")
            return

        if len(keyboard_items) >= position:
            keyboard_items[position-1] = button_data
            action = f"Updated button {position}: {title}"
        else:
            keyboard_items.append(button_data)
            action = f"Added button {position}: {title}"

        save_keyboard(keyboard_items)
        titles = "\n".join([f"{i+1}. {it['title']}" for i, it in enumerate(keyboard_items)])
        update.message.reply_text(
            f"{action}\n\nCurrent Keyboard:\n{titles}",
            reply_markup=ReplyKeyboardMarkup([[it["title"]] for it in keyboard_items], resize_keyboard=True)
        )
    return add_button

for i in range(1, 11):
    dispatcher.add_handler(CommandHandler(f"scarkeyboard{i}", create_add_button_handler(i)))

# ---------- Broadcast ----------
@owner_only
def broadcast(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to message to broadcast.")
        return

    users = load_users()
    success = failed = 0
    update.message.reply_text(f"Sending to {len(users)} users...")
    for uid in users:
        try:
            msg.copy(uid)
            success += 1
        except:
            failed += 1
        time.sleep(0.05)
    update.message.reply_text(f"Done! Success: {success} | Failed: {failed}")

# ---------- /scarqueen1 - Update Welcome with Inline Buttons ----------
@owner_only
def scarqueen1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to a photo/video/document with caption containing links!")
        return

    # Get media file_id
    photo_id = None
    if msg.photo:
        photo_id = msg.photo[-1].file_id
    elif msg.video:
        photo_id = msg.video.file_id
    elif msg.document:
        photo_id = msg.document.file_id
    else:
        update.message.reply_text("Please reply to a photo, video or document!")
        return

    raw_caption = msg.caption or ""
    
    # Extract all URL - Title pairs
    buttons = []
    clean_lines = []
    for line in raw_caption.split("\n"):
        match = re.search(r"(https?://[^\s]+)\s*[-–—:–]*\s*(.+)", line)
        if match:
            url = match.group(1).strip()
            title = match.group(2).strip()
            if title:
                buttons.append({"url": url, "text": title})
        else:
            if line.strip():
                clean_lines.append(line.strip())

    clean_caption = "\n".join(clean_lines) if clean_lines else "Lusty flirt"

    save_welcome(photo_id, clean_caption, buttons)
    global welcome_data
    welcome_data = load_welcome()

    # Preview
    inline_kb = [[InlineKeyboardButton(b["text"], url=b["url"])] for b in buttons]
    markup = InlineKeyboardMarkup(inline_kb) if inline_kb else None

    try:
        if msg.photo:
            bot.send_photo(update.effective_chat.id, photo_id, caption=clean_caption or "Welcome Updated!", reply_markup=markup, parse_mode="HTML")
        elif msg.video:
            bot.send_video(update.effective_chat.id, photo_id, caption=clean_caption, reply_markup=markup)
        elif msg.document:
            bot.send_document(update.effective_chat.id, photo_id, caption=clean_caption, reply_markup=markup)
    except:
        pass

    update.message.reply_text("Welcome message with inline buttons updated successfully!")

# ---------- Block Random Text (Non-Button, Non-Command) ----------
def block_random_text(update: Update, context: CallbackContext):
    text = update.message.text.strip() if update.message.text else ""
    
    # Allow if it's a registered keyboard button
    if any(item["title"] == text for item in keyboard_items):
        return  # Let handle_button_click deal with it
    
    # Allow commands
    if update.message.entities and any(e.type == "bot_command" for e in update.message.entities):
        return

    update.message.reply_text("send /start for main menu")

# ---------- Handlers ----------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("scarqueen", broadcast))
dispatcher.add_handler(CommandHandler("scarqueen1", scarqueen1))

# Handle keyboard button clicks
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_button_click))

# Block any random text/symbol/number
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, block_random_text), group=1)

# Block any non-text (stickers, voice, etc.)
dispatcher.add_handler(MessageHandler(~Filters.command & ~Filters.text, lambda u, c: u.message.reply_text("send /start for main menu")))

# ---------- Webhook ----------
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    if update:
        dispatcher.process_update(update)
    return '', 200

@app.route('/')
def index():
    return 'Bot is running!'

def set_webhook():
    info = bot.get_webhook_info()
    if info.url != WEBHOOK_URL:
        bot.set_webhook(url=WEBHOOK_URL)

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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)