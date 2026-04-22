import os
import io
import zipfile
from flask import Flask, request
import telebot
from telebot import types

# التوكن الخاص بك
TOKEN = "8297443710:AAE_snJB3bfKj5-bn-rrv0VeWXwN972LxgY"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- قوالب الأكواد للبوتات التي سيصنعها المستخدمون ---

def get_bot_template(user_token):
    return f"""
import os
from flask import Flask, request
import telebot

TOKEN = "{user_token}"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "✅ تم تشغيل بوتك بنجاح على Vercel عبر Bot Factory!")

@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.reply_to(message, f"وصلت رسالتك: {{message.text}}")

@app.route("/")
def index():
    return "Bot is Running!", 200
"""

# --- أوامر البوت الرئيسي (المصنع) ---

@bot.message_handler(commands=['start'])
def welcome(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🤖 صنع بوت جديد", callback_data="create"))
    bot.reply_to(message, "أهلاً بك في Bot Factory! 🛠️\n\nأنا بوت متخصص في إنشاء بوتات تعمل على Vercel بنظام Webhook.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "create")
def ask_token(call):
    msg = bot.send_message(call.message.chat.id, "📩 من فضلك أرسل توكن البوت الجديد الآن:")
    bot.register_next_step_handler(msg, generate_zip)

def generate_zip(message):
    user_token = message.text.strip()
    if ":" not in user_token:
        bot.reply_to(message, "❌ التوكن يبدو غير صحيح، تأكد من إرسال التوكن كاملاً.")
        return

    # إنشاء ملف ZIP يحتوي على ملفات Vercel كاملة
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        z.writestr("main.py", get_bot_template(user_token))
        z.writestr("requirements.txt", "pyTelegramBotAPI\nflask")
        z.writestr("vercel.json", '{"rewrites": [{"source": "/(.*)", "destination": "main.py"}]}')
        z.writestr("README.md", "1. ارفع هذه الملفات على GitHub.\n2. اربطها بـ Vercel.\n3. فعل الـ Webhook الخاص بالبوت الجديد.")

    buffer.seek(0)
    bot.send_document(message.chat.id, buffer, visible_file_name="Vercel_Bot_Project.zip", 
                     caption="🚀 إليك مشروع البوت جاهزاً!\nقم بتحميل الملف ورفعه على Vercel.")

# --- إعدادات استقبال الرسائل (الربط مع الـ Webhook) ---

@app.route('/' + TOKEN, methods=['POST'])
def receive_update():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return '', 403

@app.route('/')
def home():
    return "Bot Factory Server is Live!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
