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
import io

# ==================== CONFIGURATION ====================
TOKEN = '7395644561:AAHbnbmat32evyDtDztbmb4EAWcPktsi6nY'
CHANNEL_USERNAME = '@allconvert1'
ADMIN_IDS = [6611726859]  # Add your admin IDs here [123456789, 987654321]

# File Settings
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
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

# User sessions for multi-image PDF
user_sessions = defaultdict(lambda: {
    'images': [],
    'waiting': False,
    'created_at': None,
    'history': []
})

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== FLASK SERVER ====================
bot = telebot.TeleBot(TOKEN)
app = Flask('')

@app.route('/')
def home():
    uptime = datetime.now() - stats['start_time']
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Image to PDF Bot</title>
        <style>
            body {{ font-family: Arial; padding: 20px; background: #f0f0f0; }}
            .container {{ background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: auto; }}
            h1 {{ color: #2196F3; }}
            .stat {{ padding: 10px; margin: 10px 0; background: #e3f2fd; border-radius: 5px; }}
            .online {{ color: #4CAF50; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Image to PDF Bot</h1>
            <p class="online">● Status: ONLINE</p>
            <div class="stat">⏱ Uptime: {uptime}</div>
            <div class="stat">👥 Total Users: {len(stats['total_users'])}</div>
            <div class="stat">🔄 Total Conversions: {stats['total_conversions']}</div>
            <div class="stat">📸 Images Processed: {stats['total_images_processed']}</div>
            <div class="stat">🕐 Started: {stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return {"status": "healthy", "uptime": str(datetime.now() - stats['start_time'])}

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    logger.info("✅ Flask server started")

# ==================== HELPER FUNCTIONS ====================
def check_subscription(user_id):
    """Check if user has joined the channel"""
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception as e:
        logger.error(f"Subscription check error for {user_id}: {e}")
        return False

def is_admin(user_id):
    """Check if user is admin"""
    return user_id in ADMIN_IDS

def check_rate_limit(user_id):
    """Rate limiting check"""
    current_time = time.time()
    last_time = user_last_request[user_id]
    
    if current_time - last_time < RATE_LIMIT_SECONDS:
        return False, int(RATE_LIMIT_SECONDS - (current_time - last_time))
    
    user_last_request[user_id] = current_time
    return True, 0

def cleanup_files(user_id):
    """Delete user's temporary files"""
    try:
        for file in os.listdir(TEMP_DIR):
            if str(user_id) in file:
                os.remove(os.path.join(TEMP_DIR, file))
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def get_user_folder(user_id):
    """Create separate folder for each user"""
    user_folder = os.path.join(TEMP_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def compress_image(img_path, quality=85):
    """Compress image to reduce file size"""
    try:
        img = Image.open(img_path)
        
        # Convert RGBA to RGB if necessary
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        # Compress and save
        compressed_path = img_path.replace('.jpg', '_compressed.jpg')
        img.save(compressed_path, 'JPEG', quality=quality, optimize=True)
        return compressed_path
    except Exception as e:
        logger.error(f"Compression error: {e}")
        return img_path

def save_user_data(user_id):
    """Save user preferences and history"""
    try:
        data = {
            'preferences': user_preferences[user_id],
            'history': user_sessions[user_id]['history'][-50:]  # Keep last 50
        }
        file_path = os.path.join(DATA_DIR, f"{user_id}.json")
        with open(file_path, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Save user data error: {e}")

def load_user_data(user_id):
    """Load user preferences and history"""
    try:
        file_path = os.path.join(DATA_DIR, f"{user_id}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                data = json.load(f)
                user_preferences[user_id] = data.get('preferences', user_preferences[user_id])
                user_sessions[user_id]['history'] = data.get('history', [])
    except Exception as e:
        logger.error(f"Load user data error: {e}")

def update_stats(user_id):
    """Update statistics"""
    stats['total_users'].add(user_id)
    today = datetime.now().strftime('%Y-%m-%d')
    hour = datetime.now().strftime('%Y-%m-%d %H:00')
    stats['daily_conversions'][today] += 1
    stats['hourly_stats'][hour] += 1

def get_file_size_mb(file_path):
    """Get file size in MB"""
    return os.path.getsize(file_path) / (1024 * 1024)

# ==================== KEYBOARD HELPERS ====================
def get_main_menu():
    """Main menu keyboard"""
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("📸 Convert Image", "⚙️ Settings")
    keyboard.row("📊 My Stats", "❓ Help")
    return keyboard

def get_settings_keyboard():
    """Settings inline keyboard"""
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        telebot.types.InlineKeyboardButton("📄 Page Size", callback_data="set_page_size"),
        telebot.types.InlineKeyboardButton("🔄 Orientation", callback_data="set_orientation")
    )
    keyboard.add(
        telebot.types.InlineKeyboardButton("🎨 Quality", callback_data="set_quality"),
        telebot.types.InlineKeyboardButton("🗜 Compression", callback_data="toggle_compression")
    )
    keyboard.add(
        telebot.types.InlineKeyboardButton("💧 Watermark", callback_data="toggle_watermark"),
        telebot.types.InlineKeyboardButton("⚡ Auto Convert", callback_data="toggle_auto")
    )
    keyboard.add(telebot.types.InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu"))
    return keyboard

# ==================== BOT COMMANDS ====================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "User"
    load_user_data(user_id)
    stats['total_users'].add(user_id)
    
    logger.info(f"User {user_id} ({username}) started the bot")
    
    if check_subscription(user_id):
        welcome_text = f"""
👋 *Welcome {message.from_user.first_name}!*

I'm an *Advanced Image to PDF Converter Bot* with powerful features!

🎯 *Key Features:*
✅ Single & Multiple Image Conversion
✅ High-Quality PDF Output
✅ Image Compression
✅ Custom Page Sizes & Orientation
✅ Batch Processing
✅ Conversion History
✅ Custom Settings

📸 *How to Use:*
1️⃣ Send me one or more photos
2️⃣ Use buttons or type /done when finished
3️⃣ Get your PDF instantly!

⚡ *Quick Commands:*
/help - View all commands
/settings - Customize your preferences
/history - View conversion history
/stats - See your statistics

*Send a photo to get started!* 📤
"""
        bot.send_message(
            message.chat.id,
            welcome_text,
            parse_mode='Markdown',
            reply_markup=get_main_menu()
        )
    else:
        keyboard = telebot.types.InlineKeyboardMarkup()
        url = f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"
        keyboard.add(telebot.types.InlineKeyboardButton("🔔 Join Channel", url=url))
        keyboard.add(telebot.types.InlineKeyboardButton("✅ I Joined", callback_data="check_join"))
        
        bot.send_message(
            message.chat.id,
            f"⚠️ *Access Denied!*\n\nPlease join our channel first:\n{CHANNEL_USERNAME}\n\nThen click the button below to verify.",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """
📚 *Complete Bot Guide*

*🎯 Basic Commands:*
/start - Start the bot
/help - This help message
/settings - Customize preferences
/history - View your conversions
/stats - Your statistics
/cancel - Cancel current session
/done - Create PDF from images

*📸 Image Conversion:*
• *Single Image:* Send one photo → Instant PDF
• *Multiple Images:* Send multiple photos → Use /done

*⚙️ Advanced Features:*
• Custom page sizes (A4, Letter, A3, etc.)
• Portrait/Landscape orientation
• Image compression for smaller files
• Quality settings (Low/Medium/High)
• Auto-convert mode
• Watermark options

*📊 Statistics & History:*
• Track your conversions
• View conversion history
• Download previous PDFs

*🎨 Settings Options:*
• PDF Quality: Low/Medium/High
• Page Size: A4/Letter/A3/A5
• Orientation: Portrait/Landscape
• Compression: ON/OFF
• Auto Convert: ON/OFF

*⚡ Tips:*
• Send photos in order for multi-page PDFs
• Use compression for email-friendly files
• Check /settings for customization

*📝 Limits:*
• Max file size: 20MB per image
• Rate limit: 1 request per 3 seconds
• Session timeout: 30 minutes

*💬 Support:* {CHANNEL_USERNAME}
*🤖 Bot:* @convertall1_bot
    """
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['settings'])
def send_settings(message):
    if not check_subscription(message.from_user.id):
        bot.reply_to(message, "⚠️ Please join the channel first!")
        return
    
    user_id = message.from_user.id
    prefs = user_preferences[user_id]
    
    settings_text = f"""
⚙️ *Your Current Settings*

📄 *Page Size:* {prefs['page_size']}
🔄 *Orientation:* {prefs['orientation'].title()}
🎨 *Quality:* {prefs['pdf_quality'].title()}
🗜 *Compression:* {'ON ✅' if prefs['compression'] else 'OFF ❌'}
💧 *Watermark:* {'ON ✅' if prefs['watermark'] else 'OFF ❌'}
⚡ *Auto Convert:* {'ON ✅' if prefs['auto_convert'] else 'OFF ❌'}

*Tap buttons below to customize:*
    """
    
    bot.send_message(
        message.chat.id,
        settings_text,
        parse_mode='Markdown',
        reply_markup=get_settings_keyboard()
    )

@bot.message_handler(commands=['history'])
def send_history(message):
    if not check_subscription(message.from_user.id):
        bot.reply_to(message, "⚠️ Please join the channel first!")
        return
    
    user_id = message.from_user.id
    load_user_data(user_id)
    history = user_sessions[user_id]['history'][-10:]  # Last 10
    
    if not history:
        bot.reply_to(message, "📭 No conversion history yet!\n\nSend some photos to create PDFs.")
        return
    
    history_text = "📜 *Your Recent Conversions*\n\n"
    for i, item in enumerate(reversed(history), 1):
        history_text += f"{i}. 📄 {item['pages']} pages - {item['date']}\n"
    
    history_text += f"\n*Total Conversions:* {len(user_sessions[user_id]['history'])}"
    
    bot.send_message(message.chat.id, history_text, parse_mode='Markdown')

@bot.message_handler(commands=['stats'])
def send_user_stats(message):
    if not check_subscription(message.from_user.id):
        bot.reply_to(message, "⚠️ Please join the channel first!")
        return
    
    user_id = message.from_user.id
    load_user_data(user_id)
    total_conversions = len(user_sessions[user_id]['history'])
    
    stats_text = f"""
📊 *Your Statistics*

🔄 Total Conversions: {total_conversions}
📸 Images Processed: {sum(h['pages'] for h in user_sessions[user_id]['history'])}
📅 Member Since: User data available

⚙️ *Current Preferences:*
• Quality: {user_preferences[user_id]['pdf_quality'].title()}
• Page Size: {user_preferences[user_id]['page_size']}
• Compression: {'Enabled' if user_preferences[user_id]['compression'] else 'Disabled'}

Use /history to view all conversions
Use /settings to customize preferences
    """
    
    bot.send_message(message.chat.id, stats_text, parse_mode='Markdown')

@bot.message_handler(commands=['adminstats'])
def send_admin_stats(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Admin only command!")
        return
    
    uptime = datetime.now() - stats['start_time']
    today = datetime.now().strftime('%Y-%m-%d')
    
    stats_text = f"""
📊 *Admin Statistics Dashboard*

👥 *Users:*
• Total Users: {len(stats['total_users'])}
• Today's Conversions: {stats['daily_conversions'][today]}

🔄 *Conversions:*
• All Time: {stats['total_conversions']}
• Images Processed: {stats['total_images_processed']}

⏱ *System:*
• Uptime: {uptime}
• Started: {stats['start_time'].strftime('%Y-%m-%d %H:%M')}
• Temp Files: {len(os.listdir(TEMP_DIR))}

📁 *Storage:*
• User Data Files: {len(os.listdir(DATA_DIR))}

*Recent Activity:*
    """
    
    # Last 5 hours stats
    for i in range(5):
        hour = (datetime.now() - timedelta(hours=i)).strftime('%Y-%m-%d %H:00')
        count = stats['hourly_stats'].get(hour, 0)
        stats_text += f"\n• {hour}: {count} conversions"
    
    bot.send_message(message.chat.id, stats_text, parse_mode='Markdown')

@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Admin only command!")
        return
    
    msg = bot.reply_to(message, "📢 Please send the message to broadcast:")
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    sent = 0
    failed = 0
    
    status_msg = bot.reply_to(message, "📤 Broadcasting...")
    
    for user_id in stats['total_users']:
        try:
            bot.send_message(user_id, message.text)
            sent += 1
        except:
            failed += 1
    
    bot.edit_message_text(
        f"✅ Broadcast Complete!\n\n✓ Sent: {sent}\n✗ Failed: {failed}",
        message.chat.id,
        status_msg.message_id
    )

@bot.message_handler(commands=['cancel'])
def cancel_session(message):
    user_id = message.from_user.id
    if user_sessions[user_id]['images']:
        user_sessions[user_id] = {'images': [], 'waiting': False, 'created_at': None, 'history': user_sessions[user_id]['history']}
        cleanup_files(user_id)
        bot.reply_to(message, "✅ Session cancelled and all photos deleted.")
    else:
        bot.reply_to(message, "❌ No active session to cancel.")

@bot.message_handler(commands=['done'])
def create_multi_pdf(message):
    user_id = message.from_user.id
    
    if not check_subscription(user_id):
        bot.reply_to(message, f"⚠️ Join {CHANNEL_USERNAME} first!")
        return
    
    if not user_sessions[user_id]['images']:
        bot.reply_to(message, "❌ No photos sent yet! Send photos first.")
        return
    
    msg = bot.reply_to(message, "🔄 Creating PDF... Please wait.")
    
    try:
        user_folder = get_user_folder(user_id)
        pdf_path = os.path.join(user_folder, f"merged_{user_id}_{int(time.time())}.pdf")
        
        images = user_sessions[user_id]['images']
        
        # Apply compression if enabled
        if user_preferences[user_id]['compression']:
            bot.edit_message_text("🗜 Compressing images...", message.chat.id, msg.message_id)
            images = [compress_image(img, quality=70) for img in images]
        
        # Convert to PDF
        with open(pdf_path, "wb") as f:
            f.write(img2pdf.convert(images))
        
        file_size = get_file_size_mb(pdf_path)
        
        # Send PDF
        with open(pdf_path, "rb") as f:
            bot.send_document(
                message.chat.id,
                f,
                caption=f"✅ *PDF Created Successfully!*\n\n📄 Pages: {len(user_sessions[user_id]['images'])}\n💾 Size: {file_size:.2f} MB\n🎨 Quality: {user_preferences[user_id]['pdf_quality'].title()}\n\n🤖 @convertall1_bot",
                parse_mode='Markdown'
            )
        
        # Update stats and history
        stats['total_conversions'] += 1
        stats['total_images_processed'] += len(images)
        update_stats(user_id)
        
        user_sessions[user_id]['history'].append({
            'pages': len(images),
            'size': f"{file_size:.2f} MB",
            'date': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        save_user_data(user_id)
        
        bot.delete_message(message.chat.id, msg.message_id)
        
        # Cleanup
        user_sessions[user_id] = {
            'images': [],
            'waiting': False,
            'created_at': None,
            'history': user_sessions[user_id]['history']
        }
        cleanup_files(user_id)
        
        logger.info(f"Multi-PDF created for user {user_id} - {len(images)} pages")
        
    except Exception as e:
        logger.error(f"Multi-PDF creation error: {e}")
        bot.edit_message_text("❌ Error creating PDF. Please try again.", message.chat.id, msg.message_id)
        cleanup_files(user_id)

# ==================== PHOTO HANDLER ====================
@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    user_id = message.from_user.id
    
    # Subscription check
    if not check_subscription(user_id):
        bot.reply_to(message, f"⚠️ Join {CHANNEL_USERNAME} first!")
        return
    
    # Rate limiting
    can_proceed, wait_time = check_rate_limit(user_id)
    if not can_proceed:
        bot.reply_to(message, f"⏳ Please wait {wait_time} seconds.")
        return
    
    load_user_data(user_id)
    stats['total_users'].add(user_id)
    msg = bot.reply_to(message, "⏳ Processing...")
    
    try:
        # Download photo
        file_info = bot.get_file(message.photo[-1].file_id)
        
        # File size check
        if file_info.file_size > MAX_FILE_SIZE:
            bot.edit_message_text(
                "❌ File too large! Maximum 20MB allowed.",
                message.chat.id,
                msg.message_id
            )
            return
        
        downloaded_file = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        
        # Save image
        img_path = os.path.join(user_folder, f"img_{len(user_sessions[user_id]['images'])}_{int(time.time())}.jpg")
        with open(img_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        # Add to session
        user_sessions[user_id]['images'].append(img_path)
        user_sessions[user_id]['waiting'] = True
        user_sessions[user_id]['created_at'] = datetime.now()
        
        # Auto-convert if enabled and single image
        if user_preferences[user_id]['auto_convert'] and len(user_sessions[user_id]['images']) == 1:
            bot.edit_message_text("⚡ Auto-converting...", message.chat.id, msg.message_id)
            create_single_pdf(message, user_id, msg.message_id)
            return
        
        # Create keyboard
        keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            telebot.types.InlineKeyboardButton("✅ Create PDF Now", callback_data=f"create_pdf_{user_id}"),
            telebot.types.InlineKeyboardButton("➕ Add More Photos", callback_data="add_more")
        )
        keyboard.add(
            telebot.types.InlineKeyboardButton("🗑 Clear All", callback_data="clear_all"),
            telebot.types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_session")
        )
        
        bot.edit_message_text(
            f"✅ *Photo {len(user_sessions[user_id]['images'])} Saved!*\n\n📸 Total Photos: {len(user_sessions[user_id]['images'])}\n\n*What would you like to do?*",
            message.chat.id,
            msg.message_id,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        
        logger.info(f"User {user_id} sent photo. Total: {len(user_sessions[user_id]['images'])}")
        
    except Exception as e:
        logger.error(f"Photo handling error: {e}")
        bot.edit_message_text(
            "❌ Error processing image. Please try again.",
            message.chat.id,
            msg.message_id
        )
        cleanup_files(user_id)

def create_single_pdf(message, user_id, msg_id):
    """Helper function to create PDF from current images"""
    try:
        user_folder = get_user_folder(user_id)
        pdf_path = os.path.join(user_folder, f"output_{user_id}_{int(time.time())}.pdf")
        
        images = user_sessions[user_id]['images']
        
        # Apply compression if enabled
        if user_preferences[user_id]['compression']:
            images = [compress_image(img, quality=70) for img in images]
        
        # Convert to PDF
        with open(pdf_path, "wb") as f:
            f.write(img2pdf.convert(images))
        
        file_size = get_file_size_mb(pdf_path)
        
        # Send PDF
        with open(pdf_path, "rb") as f:
            bot.send_document(
                message.chat.id,
                f,
                caption=f"✅ *PDF Ready!*\n\n📄 Pages: {len(images)}\n💾 Size: {file_size:.2f} MB\n🎨 Quality: {user_preferences[user_id]['pdf_quality'].title()}\n\n🤖 @convertall1_bot",
                parse_mode='Markdown'
            )
        
        # Update stats
        stats['total_conversions'] += 1
        stats['total_images_processed'] += len(images)
        update_stats(user_id)
        
        user_sessions[user_id]['history'].append({
            'pages': len(images),
            'size': f"{file_size:.2f} MB",
            'date': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        save_user_data(user_id)
        
        bot.delete_message(message.chat.id, msg_id)
        
        # Cleanup
        user_sessions[user_id] = {
            'images': [],
            'waiting': False,
            'created_at': None,
            'history': user_sessions[user_id]['history']
        }
        cleanup_files(user_id)
        
    except Exception as e:
        logger.error(f"PDF creation error: {e}")
        bot.edit_message_text("❌ Error! Please try again.", message.chat.id, msg_id)

# ==================== TEXT MESSAGE HANDLER ====================
@bot.message_handler(func=lambda message: message.text in ["📸 Convert Image", "⚙️ Settings", "📊 My Stats", "❓ Help"])
def handle_menu_buttons(message):
    if message.text == "📸 Convert Image":
        bot.reply_to(message, "📤 Send me photos to convert into PDF!")
    elif message.text == "⚙️ Settings":
        send_settings(message)
    elif message.text == "📊 My Stats":
        send_user_stats(message)
    elif message.text == "❓ Help":
        send_help(message)

# ==================== CALLBACK HANDLERS ====================
@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def callback_check_join(call):
    if check_subscription(call.from_user.id):
        bot.answer_callback_query(call.id, "✅ Verification Successful!")
        bot.edit_message_text(
            "✅ *Verified Successfully!*\n\nYou can now send me photos to convert!",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown'
        )
        bot.send_message(call.message.chat.id, "Send a photo to get started!", reply_markup=get_main_menu())
    else:
        bot.answer_callback_query(call.id, "❌ You haven't joined yet!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("create_pdf_"))
def callback_create_pdf(call):
    user_id = int(call.data.split("_")[2])
    
    if call.from_user.id != user_id:
        bot.answer_callback_query(call.id, "This is not your session!", show_alert=True)
        return
    
    bot.answer_callback_query(call.id, "Creating PDF...")
    bot.edit_message_text("🔄 Creating your PDF...", call.message.chat.id, call.message.message_id)
    
    create_single_pdf(call.message, user_id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "add_more")
def callback_add_more(call):
    bot.answer_callback_query(call.id, "Send more photos!")
    bot.edit_message_text(
        "✅ Photos saved!\n\nSend more photos or type /done to create PDF.",
        call.message.chat.id,
        call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == "clear_all")
def callback_clear_all(call):
    user_id = call.from_user.id
    user_sessions[user_id]['images'] = []
    cleanup_files(user_id)
    bot.answer_callback_query(call.id, "All photos cleared!")
    bot.edit_message_text("🗑 All photos have been cleared.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_session")
def callback_cancel_session(call):
    user_id = call.from_user.id
    user_sessions[user_id] = {'images': [], 'waiting': False, 'created_at': None, 'history': user_sessions[user_id]['history']}
    cleanup_files(user_id)
    bot.answer_callback_query(call.id, "Session cancelled!")
    bot.edit_message_text("❌ Session cancelled.", call.message.chat.id, call.message.message_id)

# Settings callbacks
@bot.callback_query_handler(func=lambda call: call.data == "set_page_size")
def callback_page_size(call):
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    sizes = ["A4", "Letter", "A3", "A5", "Legal"]
    for size in sizes:
        keyboard.add(telebot.types.InlineKeyboardButton(size, callback_data=f"pagesize_{size}"))
    keyboard.add(telebot.types.InlineKeyboardButton("🔙 Back", callback_data="back_settings"))
    
    bot.edit_message_text(
        "📄 Select Page Size:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("pagesize_"))
def callback_set_pagesize(call):
    size = call.data.split("_")[1]
    user_preferences[call.from_user.id]['page_size'] = size
    save_user_data(call.from_user.id)
    bot.answer_callback_query(call.id, f"✅ Page size set to {size}")
    send_settings(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "set_orientation")
def callback_orientation(call):
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(
        telebot.types.InlineKeyboardButton("📄 Portrait", callback_data="orient_portrait"),
        telebot.types.InlineKeyboardButton("📃 Landscape", callback_data="orient_landscape")
    )
    keyboard.add(telebot.types.InlineKeyboardButton("🔙 Back", callback_data="back_settings"))
    
    bot.edit_message_text(
        "🔄 Select Orientation:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("orient_"))
def callback_set_orient(call):
    orient = call.data.split("_")[1]
    user_preferences[call.from_user.id]['orientation'] = orient
    save_user_data(call.from_user.id)
    bot.answer_callback_query(call.id, f"✅ Orientation set to {orient}")
    send_settings(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "set_quality")
def callback_quality(call):
    keyboard = telebot.types.InlineKeyboardMarkup()
    qualities = [("🔻 Low", "low"), ("➖ Medium", "medium"), ("🔺 High", "high")]
    for label, value in qualities:
        keyboard.add(telebot.types.InlineKeyboardButton(label, callback_data=f"quality_{value}"))
    keyboard.add(telebot.types.InlineKeyboardButton("🔙 Back", callback_data="back_settings"))
    
    bot.edit_message_text(
        "🎨 Select PDF Quality:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("quality_"))
def callback_set_quality(call):
    quality = call.data.split("_")[1]
    user_preferences[call.from_user.id]['pdf_quality'] = quality
    save_user_data(call.from_user.id)
    bot.answer_callback_query(call.id, f"✅ Quality set to {quality}")
    send_settings(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "toggle_compression")
def callback_toggle_compression(call):
    user_id = call.from_user.id
    current = user_preferences[user_id]['compression']
    user_preferences[user_id]['compression'] = not current
    save_user_data(user_id)
    status = "ON ✅" if not current else "OFF ❌"
    bot.answer_callback_query(call.id, f"Compression {status}")
    send_settings(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "toggle_watermark")
def callback_toggle_watermark(call):
    user_id = call.from_user.id
    current = user_preferences[user_id]['watermark']
    user_preferences[user_id]['watermark'] = not current
    save_user_data(user_id)
    status = "ON ✅" if not current else "OFF ❌"
    bot.answer_callback_query(call.id, f"Watermark {status}")
    send_settings(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "toggle_auto")
def callback_toggle_auto(call):
    user_id = call.from_user.id
    current = user_preferences[user_id]['auto_convert']
    user_preferences[user_id]['auto_convert'] = not current
    save_user_data(user_id)
    status = "ON ✅" if not current else "OFF ❌"
    bot.answer_callback_query(call.id, f"Auto Convert {status}")
    send_settings(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "back_settings")
def callback_back_settings(call):
    send_settings(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "main_menu")
def callback_main_menu(call):
    bot.edit_message_text(
        "🏠 Main Menu\n\nUse buttons below:",
        call.message.chat.id,
        call.message.message_id
    )
    bot.send_message(call.message.chat.id, "Choose an option:", reply_markup=get_main_menu())

# ==================== ERROR HANDLER ====================
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    bot.reply_to(message, "❌ Invalid input!\n\nUse /help or send a photo.")

# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    logger.info("🚀 Starting Advanced Image to PDF Bot...")
    keep_alive()
    logger.info("✅ Bot is now running!")
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        # Auto-restart logic can be added here
