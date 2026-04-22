import os
import io
import zipfile
from flask import Flask, request
import telebot

TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

def generate_vercel_bot_code(user_token):
    """توليد كود بوت متوافق مع نظام Serverless في Vercel"""
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

@app.route("/")
def webhook():
    # هذا المسار لتفعيل الويب هوك يدوياً عند زيارته
    return "Bot is Running!", 200

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "أهلاً بك! هذا البوت تم إنشاؤه عبر Bot Factory ويعمل على Vercel بنجاح.")

# أضف هنا باقي منطق البوت (تحميل، ترجمة.. إلخ)
"""

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "مرحباً بك في مصنع البوتات! أرسل التوكن الخاص ببوتك الجديد وسأجهز لك ملفات Vercel.")

@bot.message_handler(func=lambda m: ":" in m.text)
def handle_token(message):
    user_token = message.text.strip()
    
    # إنشاء ملف ZIP يحتوي على كل متطلبات Vercel
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        # 1. الملف الرئيسي (يجب أن يسمى api/index.py لـ Vercel أو تضبطه في vercel.json)
        z.writestr("index.py", generate_vercel_bot_code(user_token))
        
        # 2. ملف المتطلبات
        z.writestr("requirements.txt", "pyTelegramBotAPI\nflask")
        
        # 3. ملف vercel.json (أهم ملف لتوجيه الطلبات)
        vercel_config = """
{
  "rewrites": [
    { "source": "/(.*)", "destination": "index.py" }
  ]
}
        """
        z.writestr("vercel.json", vercel_config)

    buffer.seek(0)
    bot.send_document(message.chat.id, buffer, visible_file_name="Vercel_Bot.zip", 
                     caption="🚀 إليك ملفات البوت جاهزة لـ Vercel!\n\n1. ارفعها على GitHub.\n2. اربطها بـ Vercel.\n3. فعل الـ Webhook عبر الرابط الذي سأرسله لك.")

# تشغيل خادم المصنع
@app.route('/' + (TOKEN or ""), methods=['POST'])
def get_updates():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return '', 403

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
