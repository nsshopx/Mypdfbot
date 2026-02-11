import telebot
import img2pdf
import os
import logging
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
import time
from collections import defaultdict
import json
from PIL import Image

# ==================== CONFIGURATION ====================
TOKEN = '7395644561:AAHbnbmat32evyDtDztbmb4EAWcPktsi6nY'
CHANNEL_USERNAME = '@allconvert1'
ADMIN_IDS = [6611726859] 

# File Settings
MAX_FILE_SIZE = 20 * 1024 * 1024
TEMP_DIR = "temp_files"
DATA_DIR = "user_data"
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Rate Limiting
user_last_request = defaultdict(float)
RATE_LIMIT_SECONDS = 3

# Statistics
stats = {
    'total_users': set(),
    'total_conversions': 0,
    'total_images_processed': 0,
    'start_time': datetime.now(),
    'daily_conversions': defaultdict(int),
    'hourly_stats': defaultdict(int)
}

# User preferences
user_preferences = defaultdict(lambda: {
    'pdf_quality': 'high',
    'page_size': 'A4',
    'orientation': 'portrait',
    'compression': False,
    'watermark': False,
    'auto_convert': False
})

# User sessions
user_sessions = defaultdict(lambda: {
    'images': [],
    'waiting': False,
    'created_at': None,
    'history': []
})

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== FLASK SERVER (RENDER KEEPER) ====================
bot = telebot.TeleBot(TOKEN)
app = Flask('')

@app.route('/')
def home():
    return "Bot is running! 🚀"

@app.route('/health')
def health():
    return "Healthy"

# ==================== HELPER FUNCTIONS ====================
def check_subscription(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['creator', 'administrator', 'member']
    except:
        return False

def check_rate_limit(user_id):
    current_time = time.time()
    last_time = user_last_request[user_id]
    if current_time - last_time < RATE_LIMIT_SECONDS:
        return False, int(RATE_LIMIT_SECONDS - (current_time - last_time))
    user_last_request[user_id] = current_time
    return True, 0

def cleanup_files(user_id):
    try:
        for file in os.listdir(TEMP_DIR):
            if str(user_id) in file:
                os.remove(os.path.join(TEMP_DIR, file))
    except:
        pass

def get_user_folder(user_id):
    user_folder = os.path.join(TEMP_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def compress_image(img_path, quality=85):
    try:
        img = Image.open(img_path)
        if img.mode == 'RGBA': img = img.convert('RGB')
        compressed_path = img_path.replace('.jpg', '_compressed.jpg')
        img.save(compressed_path, 'JPEG', quality=quality, optimize=True)
        return compressed_path
    except:
        return img_path

def save_user_data(user_id):
    try:
        data = {'preferences': user_preferences[user_id], 'history': user_sessions[user_id]['history'][-50:]}
        with open(os.path.join(DATA_DIR, f"{user_id}.json"), 'w') as f: json.dump(data, f)
    except: pass

def load_user_data(user_id):
    try:
        path = os.path.join(DATA_DIR, f"{user_id}.json")
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
                user_preferences[user_id].update(data.get('preferences', {}))
                user_sessions[user_id]['history'] = data.get('history', [])
    except: pass

# ==================== BOT HANDLERS ====================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    load_user_data(user_id)
    stats['total_users'].add(user_id)
    
    if check_subscription(user_id):
        keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.row("📸 Convert Image", "⚙️ Settings")
        keyboard.row("📊 My Stats", "❓ Help")
        bot.send_message(message.chat.id, f"Welcome {message.from_user.first_name}! Send me a photo.", reply_markup=keyboard)
    else:
        keyboard = telebot.types.InlineKeyboardMarkup()
        url = f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"
        keyboard.add(telebot.types.InlineKeyboardButton("🔔 Join Channel", url=url))
        keyboard.add(telebot.types.InlineKeyboardButton("✅ I Joined", callback_data="check_join"))
        bot.send_message(message.chat.id, "⚠️ Please join our channel first!", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def callback_check_join(call):
    if check_subscription(call.from_user.id):
        bot.answer_callback_query(call.id, "Verified!")
        bot.send_message(call.message.chat.id, "You can now send photos!")
    else:
        bot.answer_callback_query(call.id, "Not joined yet!", show_alert=True)

@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.reply_to(message, "Join channel first!")
        return

    load_user_data(user_id)
    msg = bot.reply_to(message, "Processing... ⏳")
    
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        img_path = os.path.join(user_folder, f"{user_id}_{int(time.time())}.jpg")
        
        with open(img_path, 'wb') as f: f.write(downloaded_file)
        
        pdf_path = img_path.replace('.jpg', '.pdf')
        with open(pdf_path, "wb") as f: f.write(img2pdf.convert(img_path))
        
        with open(pdf_path, "rb") as f:
            bot.send_document(message.chat.id, f, caption="Converted by @convertall1_bot")
            
        bot.delete_message(message.chat.id, msg.message_id)
        cleanup_files(user_id)
        stats['total_conversions'] += 1
    except Exception as e:
        bot.reply_to(message, "Error converting image.")
        logger.error(e)
        cleanup_files(user_id)

# ==================== MAIN EXECUTION ====================
def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    # 1. Start Bot in Background Thread
    t = Thread(target=run_bot)
    t.start()
    
    # 2. Start Flask in MAIN Thread (This fixes Port Timeout)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

