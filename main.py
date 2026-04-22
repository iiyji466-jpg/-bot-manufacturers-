import os
import io
import zipfile
from flask import Flask, request
import telebot
from telebot import types

# إعداد التطبيق والتوكن
TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# تخزين مؤقت لبيانات المستخدم (في الإنتاج يفضل استخدام قاعدة بيانات)
user_data = {}

# --- القوالب الجاهزة (Templates) ---

TEMPLATES = {
    "1": {"name": "بوت ردود بسيط", "file": "simple_bot.py"},
    "2": {"name": "بوت تحميل ميديا", "file": "downloader_bot.py"},
    "3": {"name": "بوت ترجمة", "file": "translator_bot.py"}
}

def generate_bot_code(template_id, user_token, welcome_msg):
    """توليد كود البوت بناءً على القالب"""
    if template_id == "1":
        return f"""
import telebot
bot = telebot.TeleBot("{user_token}")

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "{welcome_msg}")

@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.reply_to(message, "لقد أرسلت: " + message.text)

bot.infinity_polling()
"""
    # يمكنك إضافة أكواد القوالب الأخرى هنا بنفس الطريقة
    return ""

# --- لوحة التحكم والأوامر ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup()
    item = types.InlineKeyboardButton("🤖 صنع بوت جديد", callback_data="create_bot")
    markup.add(item)
    bot.reply_to(message, "أهلاً بك في Bot Factory! 🛠️\nاصنع بوتك الخاص الآن بدون كود.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "create_bot")
def choose_template(call):
    markup = types.InlineKeyboardMarkup()
    for k, v in TEMPLATES.items():
        markup.add(types.InlineKeyboardButton(v['name'], callback_data=f"tpl_{k}"))
    bot.edit_message_text("🎯 اختر نوع البوت الذي تريد إنشاءه:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("tpl_"))
def get_token(call):
    template_id = call.data.split("_")[1]
    user_data[call.from_user.id] = {'template_id': template_id}
    msg = bot.send_message(call.message.chat.id, "📩 أرسل الآن توكن البوت (من @BotFather):")
    bot.register_next_step_handler(msg, process_token)

def process_token(message):
    user_id = message.from_user.id
    if message.text and ":" in message.text:
        user_data[user_id]['token'] = message.text
        msg = bot.send_message(message.chat.id, "✍️ أدخل رسالة الترحيب التي سيقولها البوت:")
        bot.register_next_step_handler(msg, process_welcome_msg)
    else:
        bot.reply_to(message, "❌ التوكن غير صحيح، حاول مجدداً /start")

def process_welcome_msg(message):
    user_id = message.from_user.id
    user_data[user_id]['welcome'] = message.text
    
    # إنشاء ملف الـ ZIP في الذاكرة
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        # 1. كود البوت
        bot_code = generate_bot_code(user_data[user_id]['template_id'], user_data[user_id]['token'], message.text)
        z.writestr("main.py", bot_code)
        
        # 2. ملف المتطلبات
        z.writestr("requirements.txt", "pyTelegramBotAPI\nrequests")
        
        # 3. ملف تعليمات النشر
        readme = """
# تعليمات النشر على Render
1. ارفع هذه الملفات على GitHub.
2. اربط حسابك في Render بمستودع GitHub.
3. اختر 'Web Service'.
4. استخدم الأمر 'python main.py' للتشغيل.
        """
        z.writestr("README.md", readme)

    buffer.seek(0)
    bot.send_document(message.chat.id, buffer, visible_file_name="MyNewBot.zip", caption="🚀 تم إنشاء بوتك بنجاح! حمل الملف وانشره على Render.")

# --- إعدادات Vercel و Flask ---

@app.route('/' + (TOKEN or ""), methods=['POST'])
def get_updates():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return '', 403

@app.route('/')
def index():
    return "Bot Factory is Online!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
