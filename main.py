import telebot
import img2pdf
import os

# --- आपकी डिटेल्स (Auto-Filled from Screenshots) ---
TOKEN = '7395644561:AAHbnbmat32evyDtDztbmb4EAWcPktsi6nY'
CHANNEL_USERNAME = '@allconvert1' 
# ---------------------------------------------------

bot = telebot.TeleBot(TOKEN)

# 1. Force Subscribe Check Function (यह चेक करेगा कि यूजर मेंबर है या नहीं)
def check_subscription(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        # अगर यूजर क्रिएटर, एडमिन या मेंबर है, तो True
        if member.status in ['creator', 'administrator', 'member']:
            return True
        else:
            return False
    except Exception as e:
        # अगर बॉट चैनल में एडमिन नहीं है, तो यह एरर आएगा
        print(f"Error: {e} (Check if bot is Admin in channel)")
        return False

# 2. Start Command (वेलकम मैसेज)
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    if check_subscription(user_id):
        bot.reply_to(message, f"नमस्ते {first_name}! 👋\n\nमैं तैयार हूँ! मुझे कोई भी **Photo (Image)** भेजें, मैं उसे **PDF** बना दूंगा।")
    else:
        # अगर जॉइन नहीं किया तो ये बटन दिखाओ
        keyboard = telebot.types.InlineKeyboardMarkup()
        
        # चैनल का लिंक (t.me/allconvert1)
        channel_url = f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"
        
        btn1 = telebot.types.InlineKeyboardButton(text="🔔 Join Channel First", url=channel_url)
        btn2 = telebot.types.InlineKeyboardButton(text="✅ I have Joined", callback_data="check_join")
        keyboard.add(btn1)
        keyboard.add(btn2)
        
        bot.send_message(message.chat.id, 
                         f"⚠️ **एक्सेस नहीं मिला!**\n\nइस बॉट को यूज़ करने के लिए आपको हमारा चैनल {CHANNEL_USERNAME} जॉइन करना होगा।", 
                         reply_markup=keyboard)

# 3. 'I have Joined' बटन का लॉजिक
@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def callback_query(call):
    if check_subscription(call.from_user.id):
        bot.answer_callback_query(call.id, "सत्यापन सफल रहा! ✅")
        bot.send_message(call.message.chat.id, "शुक्रिया! अब आप मुझे Photos भेज सकते हैं। 📸")
    else:
        bot.answer_callback_query(call.id, "आपने अभी तक जॉइन नहीं किया है! ❌", show_alert=True)

# 4. फोटो से PDF बनाने का लॉजिक
@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    user_id = message.from_user.id
    
    # डबल चेक: क्या यूजर अभी भी चैनल में है?
    if not check_subscription(user_id):
        bot.reply_to(message, f"कृपया पहले चैनल जॉइन करें: {CHANNEL_USERNAME}")
        return

    msg = bot.reply_to(message, "Photo मिल गयी! ⏳ PDF बना रहा हूँ...")

    try:
        # फाइल डाउनलोड
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # फाइल के नाम
        img_path = f"temp_{user_id}.jpg"
        pdf_path = f"{user_id}_converted.pdf"
        
        # फोटो सेव करना
        with open(img_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        # PDF में कन्वर्ट करना
        with open(pdf_path, "wb") as f:
            f.write(img2pdf.convert(img_path))
            
        # PDF यूजर को भेजना
        with open(pdf_path, "rb") as f:
            bot.send_document(message.chat.id, f, caption="ये रही आपकी PDF फाइल! 📄\nConverted by @convertall1_bot")
        
        # "Processing" वाला मैसेज डिलीट करना (ताकि चैट साफ़ रहे)
        bot.delete_message(message.chat.id, msg.message_id)

        # सर्वर से फाइल डिलीट (Cleanup)
        os.remove(img_path)
        os.remove(pdf_path)

    except Exception as e:
        bot.reply_to(message, "कुछ गड़बड़ हो गयी। कृपया दोबारा कोशिश करें।")
        print(f"Error: {e}")

# बॉट स्टार्ट
print("Bot is running... (Press Ctrl+C to stop)")
bot.polling()
