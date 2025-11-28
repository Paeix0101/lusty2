import os
import json
import logging
import threading
import time
import requests
import re

from flask import Flask, request
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler

# --------------------- CONFIG ---------------------
TOKEN = os.getenv("BOT_TOKEN")
OWNER_IDS = {8183414512, 6218772339, 8141547148, 7514171886}

USERS_FILE = "users.txt"
WELCOME_FILE = "welcome.json"
KEYBOARD_FILE = "keyboard.json"
CHANNELS_FILE = "channels.json"   # Force join channels

WEBHOOK_URL = f"https://lusty2.onrender.com/{TOKEN}"
# --------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

lock = threading.Lock()

# ---------- Load/Save Functions ----------
def load_json(file, default):
    if not os.path.exists(file):
        return default
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

# Load data
welcome_data = load_json(WELCOME_FILE, {"photo": None, "caption": "Welcome!", "buttons": []})
reply_keyboard_buttons = load_json(KEYBOARD_FILE, [])
force_channels = load_json(CHANNELS_FILE, [])  # List of {"id": -1001234567890, "link": "https://t.me/channel"}

# ---------- Users ----------
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

# ---------- Check if User Joined All Channels ----------
async def check_subscription(user_id):
    if not force_channels:
        return True
    for channel in force_channels:
        try:
            member = await bot.get_chat_member(chat_id=channel["id"], user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

# ---------- Extract Links from Caption ----------
def extract_links_from_caption(caption):
    if not caption:
        return [], "Welcome!"
    pattern = r"(https?://[^\s]+)\s*-?\s*([^\n\r]+)"
    matches = re.findall(pattern, caption)
    buttons = []
    clean_caption = caption

    for url, title in matches:
        title = title.strip(" -")
        if not title:
            title = "Open Link"
        buttons.append({"url": url.strip(), "text": title})
        clean_caption = re.sub(re.escape(url) + r".*" + re.escape(title), "", clean_caption).strip()

    if not buttons:
        lines = [l.strip() for l in caption.splitlines() if "http" in l]
        for line in lines:
            parts = line.split()
            url = next((p for p in parts if p.startswith("http")), None)
            if url:
                title = " ".join([p for p in parts if p != url]) or "Join Here"
                buttons.append({"url": url, "text": title})
                clean_caption = clean_caption.replace(line, "").strip()

    return buttons, clean_caption or "Welcome!"

# ---------- /start ----------
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    uid = user.id
    save_user(uid)
    forward_id(uid)

    is_subscribed = await check_subscription(uid)

    if not is_subscribed:
        keyboard = []
        for ch in force_channels:
            keyboard.append([InlineKeyboardButton(f"Join {ch.get('name', 'Channel')}", url=ch["link"])])
        keyboard.append([InlineKeyboardButton("I Joined – Refresh", callback_data="check_join")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Please join our channels first to unlock the bot!",
            reply_markup=reply_markup
        )
        return

    # User is subscribed → show main menu
    photo = welcome_data["photo"]
    caption = welcome_data["caption"]
    buttons_data = welcome_data["buttons"]

    inline_keyboard = [
        [InlineKeyboardButton(btn["text"], url=btn["url"]) for btn in row]
        for row in [buttons_data[i:i+2] for i in range(0, len(buttons_data), 2)]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard) if inline_keyboard else None

    try:
        if photo:
            await bot.send_photo(chat_id=uid, photo=photo, caption=caption, reply_markup=reply_markup)
        else:
            await bot.send_message(chat_id=uid, text=caption or "Welcome!", reply_markup=reply_markup)
    except:
        await bot.send_message(chat_id=uid, text=caption or "Welcome!", reply_markup=reply_markup)

    # Persistent keyboard
    if reply_keyboard_buttons:
        kb = [[KeyboardButton(btn["text"])] for btn in reply_keyboard_buttons]
        await bot.send_message(chat_id=uid, text="Your Menu:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

# ---------- Refresh Button ----------
async def check_join_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if await check_subscription(user_id):
        await query.edit_message_text("Access Granted! Sending menu...")
        await start(update, context)  # Reuse start logic
    else:
        await query.edit_message_text("You haven't joined all channels yet!")

# ---------- /scarqueen1 - Set Welcome + Inline Buttons ----------
@owner_only
async def scarqueen1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg or not msg.photo:
        update.message.reply_text("Reply to a photo with caption:\nhttps://link - Button Name")
        return

    photo = msg.photo[-1].file_id
    caption = msg.caption or ""
    buttons, clean_caption = extract_links_from_caption(caption)

    save_json(WELCOME_FILE, {"photo": photo, "caption": clean_caption, "buttons": buttons})
    global welcome_data
    welcome_data = load_json(WELCOME_FILE, welcome_data)

    update.message.reply_text(f"Welcome Updated!\nButtons: {len(buttons)}")

# ---------- /scarkeyboard1 - Set Bottom Keyboard ----------
@owner_only
async def scarkeyboard1(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg or not msg.text:
        update.message.reply_text("Reply to text:\nhttps://link.com - Button Name")
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

    save_json(KEYBOARD_FILE, buttons)
    global reply_keyboard_buttons
    reply_keyboard_buttons = buttons

    kb = [[KeyboardButton(b["text"])] for b in buttons]
    update.message.reply_text("Keyboard Updated!", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

# ---------- /setchannels - Set Force Join Channels ----------
@owner_only
async def setchannels(update: Update, context: CallbackContext):
    if not context.args:
        update.message.reply_text("Usage: /setchannels @channel1 @channel2")
        return

    channels = []
    for username in context.args:
        username = username.replace("https://t.me/", "").replace("@", "")
        try:
            chat = await bot.get_chat("@" + username)
            channels.append({
                "id": chat.id,
                "link": f"https://t.me/{username}",
                "name": chat.title
            })
        except:
            update.message.reply_text(f"Failed to add {username}")
            continue

    save_json(CHANNELS_FILE, channels)
    global force_channels
    force_channels = channels

    text = "Force Join Channels Updated:\n" + "\n".join([f"• {c['name']}" for c in channels])
    update.message.reply_text(text)

# ---------- Broadcast ----------
@owner_only
async def scarqueen(update: Update, context: CallbackContext):
    msg = update.message.reply_to_message
    if not msg:
        update.message.reply_text("Reply to a message/photo!")
        return

    users = load_users()
    success = failed = 0
    text = msg.caption or msg.text or ""
    photo = msg.photo[-1].file_id if msg.photo else None

    update.message.reply_text(f"Broadcasting to {len(users)} users...")

    for uid in users:
        try:
            if photo:
                await bot.send_photo(uid, photo, caption=text)
            else:
                await bot.send_message(uid, text)
            success += 1
        except:
            failed += 1
        time.sleep(0.05)

    update.message.reply_text(f"Broadcast Done!\nSuccess: {success}\nFailed: {failed}")

# ---------- Handlers ----------
dispatcher.add_handler(CommandHandler("start", start, run_async=True))
dispatcher.add_handler(CallbackQueryHandler(check_join_callback, pattern="check_join"))
dispatcher.add_handler(CommandHandler("scarqueen1", scarqueen1, run_async=True))
dispatcher.add_handler(CommandHandler("scarkeyboard1", scarkeyboard1, run_async=True))
dispatcher.add_handler(CommandHandler("setchannels", setchannels, run_async=True))
dispatcher.add_handler(CommandHandler("scarqueen", scarqueen, run_async=True))
dispatcher.add_handler(MessageHandler(Filters.all & ~Filters.command, lambda u, c: u.message.reply_text("Send /start")))

# ---------- Webhook & Keep Alive ----------
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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)