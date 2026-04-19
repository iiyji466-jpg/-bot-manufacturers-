# bot_factory.py - الإصدار النهائي المتكامل (قوالب + حزمة ZIP + إشارات إنهاء نظيفة)
import os
import json
import logging
import re
import threading
import subprocess
import sys
import asyncio
import signal
import zipfile
import io
from http.server import HTTPServer, BaseHTTPRequestHandler

import telegram
print(f"✅ إصدار python-telegram-bot: {telegram.__version__}")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ===== مراحل المحادثة =====
(
    STEP_TEMPLATE,           # اختيار نوع القالب
    STEP_TOKEN,
    STEP_WELCOME,
    STEP_CMD_CHOICE,
    STEP_CMD_NAME,
    STEP_CMD_REPLY,
    STEP_CMD_MORE,
    STEP_AUTO_CHOICE,
    STEP_AUTO_KEYWORD,
    STEP_AUTO_REPLY,
    STEP_AUTO_MORE,
    STEP_SCHEDULE_CHOICE,
    STEP_SCHEDULE_CHAT,
    STEP_SCHEDULE_MSG,
    STEP_SCHEDULE_INTERVAL,
    STEP_API_KEYS,           # طلب مفاتيح API
    STEP_CONFIRM,
) = range(18)

store = {}

# ===== تعريف القوالب =====
TEMPLATES = {
    "simple": {
        "name": "🤖 بوت أوامر وردود بسيط",
        "description": "أوامر مخصصة، ردود تلقائية، وجدولة.",
        "needs_api": False,
        "api_keys": []
    },
    "downloader": {
        "name": "⬇️ بوت تحميل (YouTube, Instagram)",
        "description": "أرسل رابطًا وسيقوم البوت بتحميل الفيديو.",
        "needs_api": False,
        "api_keys": []
    },
    "translator": {
        "name": "🌐 بوت ترجمة فورية",
        "description": "يكتب المستخدم نصًا ويترجمه إلى العربية أو الإنجليزية.",
        "needs_api": False,   # googletrans مجاني بدون API
        "api_keys": []
    },
    "chatgpt": {
        "name": "🧠 بوت محادثة ذكي (ChatGPT)",
        "description": "يتحدث مع المستخدم باستخدام OpenAI API.",
        "needs_api": True,
        "api_keys": ["OPENAI_API_KEY"]
    }
}

# ===== لوحات المفاتيح =====
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 صنع بوت جديد", callback_data="new_bot")],
        [InlineKeyboardButton("📋 بوتاتي", callback_data="my_bots")],
    ])

def template_menu():
    keyboard = []
    for key, data in TEMPLATES.items():
        keyboard.append([InlineKeyboardButton(data["name"], callback_data=f"tpl_{key}")])
    return InlineKeyboardMarkup(keyboard)

def yes_no():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم", callback_data="yes"),
         InlineKeyboardButton("❌ لا", callback_data="no")]
    ])

# ===== دوال المحادثة الأساسية =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *أهلاً! أنا بوت صانع البوتات*\n\n"
        "بدون كود، أصنع لك بوت Telegram احترافي!\n\n"
        "اختر من القائمة:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

async def show_my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bots_dir = "bots"
    if not os.path.exists(bots_dir) or not os.listdir(bots_dir):
        await query.edit_message_text("📭 ما عندك بوتات بعد!\n\nاضغط /start لتصنع بوت.")
    else:
        bots = [f for f in os.listdir(bots_dir) if f.endswith('.py')]
        if not bots:
            await query.edit_message_text("📭 ما عندك بوتات بعد!")
        else:
            text = "📋 *بوتاتك:*\n\n" + "\n".join([f"• `{b[:-3]}`" for b in bots])
            await query.edit_message_text(text, parse_mode="Markdown")

async def new_bot_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    store[uid] = {
        "template": "simple",  # افتراضي
        "token": "", "welcome": "", "commands": {},
        "auto_replies": {}, "schedule": [], "api_keys": {}
    }
    await query.edit_message_text(
        "📌 *اختر نوع البوت الذي تريد صنعه:*\n\n"
        "كل نوع يأتي بوظائف جاهزة. اختر ما يناسبك:",
        parse_mode="Markdown",
        reply_markup=template_menu()
    )
    return STEP_TEMPLATE

async def choose_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    template_key = query.data.replace("tpl_", "")
    store[uid]["template"] = template_key
    template = TEMPLATES[template_key]

    # إذا كان القالب يحتاج مفاتيح API
    if template["needs_api"]:
        store[uid]["needed_keys"] = template["api_keys"].copy()
        await query.edit_message_text(
            f"✅ اخترت: *{template['name']}*\n\n"
            f"{template['description']}\n\n"
            f"هذا البوت يحتاج بعض المفاتيح للعمل.\n"
            f"سأطلب منك لاحقًا: {', '.join(template['api_keys'])}\n\n"
            "🔑 *الخطوة 1: توكن البوت*\n"
            "أرسل التوكن الذي حصلت عليه من @BotFather:",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            f"✅ اخترت: *{template['name']}*\n\n"
            f"{template['description']}\n\n"
            "🔑 *الخطوة 1: توكن البوت*\n"
            "أرسل التوكن الذي حصلت عليه من @BotFather:",
            parse_mode="Markdown"
        )
    return STEP_TOKEN

async def get_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    token = update.message.text.strip()
    if ":" not in token or len(token) < 30:
        await update.message.reply_text("⚠️ التوكن غير صحيح، أرسله مرة أخرى.")
        return STEP_TOKEN
    try:
        from telegram import Bot
        me = await Bot(token=token).get_me()
        store[uid]["token"] = token
        template = TEMPLATES[store[uid]["template"]]

        # إذا كان القالب يحتاج API keys
        if template["needs_api"] and store[uid].get("needed_keys"):
            next_key = store[uid]["needed_keys"][0]
            await update.message.reply_text(
                f"✅ التوكن صحيح. اسم البوت: @{me.username}\n\n"
                f"🔐 *مطلوب مفتاح API:* `{next_key}`\n\n"
                f"أرسل قيمة `{next_key}` الآن:",
                parse_mode="Markdown"
            )
            return STEP_API_KEYS

        # وإلا ننتقل لرسالة الترحيب
        await update.message.reply_text(
            f"✅ تم! اسم البوت: @{me.username}\n\n"
            "💬 *رسالة الترحيب*\n\n"
            "ما الرسالة التي تظهر عند كتابة /start في بوتك؟",
            parse_mode="Markdown"
        )
        return STEP_WELCOME
    except Exception as e:
        await update.message.reply_text(f"❌ التوكن غير صالح: {e}\nأرسل توكن صحيح:")
        return STEP_TOKEN

async def get_api_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    value = update.message.text.strip()

    current_key = store[uid]["needed_keys"].pop(0)
    store[uid]["api_keys"][current_key] = value

    if store[uid]["needed_keys"]:
        next_key = store[uid]["needed_keys"][0]
        await update.message.reply_text(
            f"✅ تم حفظ `{current_key}`\n\n"
            f"🔐 *المفتاح التالي:* `{next_key}`\n"
            f"أرسل القيمة:",
            parse_mode="Markdown"
        )
        return STEP_API_KEYS
    else:
        await update.message.reply_text(
            "✅ تم حفظ جميع المفاتيح!\n\n"
            "💬 *رسالة الترحيب*\n\n"
            "ما الرسالة التي تظهر عند كتابة /start في بوتك؟",
            parse_mode="Markdown"
        )
        return STEP_WELCOME

async def get_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    store[uid]["welcome"] = update.message.text.strip()

    if store[uid]["template"] == "simple":
        await update.message.reply_text(
            "✅ تم!\n\n"
            "⚙️ *الأوامر المخصصة*\n\n"
            "هل تريد إضافة أوامر؟",
            parse_mode="Markdown",
            reply_markup=yes_no()
        )
        return STEP_CMD_CHOICE
    else:
        return await show_summary(update, context)

# ===== دوال الأوامر المخصصة =====
async def cmd_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "yes":
        await query.edit_message_text("📝 أرسل اسم الأمر بدون / مثل: `price`", parse_mode="Markdown")
        return STEP_CMD_NAME
    else:
        await query.edit_message_text(
            "🤖 *الردود التلقائية*\n\n"
            "هل تريد إضافة ردود تلقائية على كلمات معينة؟",
            parse_mode="Markdown",
            reply_markup=yes_no()
        )
        return STEP_AUTO_CHOICE

async def get_cmd_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.strip().replace("/", "").lower()
    if not cmd:
        await update.message.reply_text("⚠️ أرسل اسم صالح للأمر.")
        return STEP_CMD_NAME
    context.user_data["cmd"] = cmd
    await update.message.reply_text(f"✅ الأمر: `/{cmd}`\n\nأرسل الرد:", parse_mode="Markdown")
    return STEP_CMD_REPLY

async def get_cmd_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cmd = context.user_data["cmd"]
    store[uid]["commands"][cmd] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ تم حفظ `/{cmd}`\n\nتريد إضافة أمر آخر؟",
        parse_mode="Markdown",
        reply_markup=yes_no()
    )
    return STEP_CMD_MORE

async def cmd_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "yes":
        await query.edit_message_text("📝 أرسل اسم الأمر الجديد:")
        return STEP_CMD_NAME
    else:
        await query.edit_message_text(
            "🤖 *الردود التلقائية*\n\n"
            "هل تريد إضافة ردود تلقائية على كلمات معينة؟",
            parse_mode="Markdown",
            reply_markup=yes_no()
        )
        return STEP_AUTO_CHOICE

# ===== دوال الردود التلقائية =====
async def auto_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "yes":
        await query.edit_message_text("🔍 أرسل الكلمة المفتاحية:\nمثال: `مرحبا`", parse_mode="Markdown")
        return STEP_AUTO_KEYWORD
    else:
        await query.edit_message_text(
            "⏰ *جدولة الرسائل*\n\n"
            "هل تريد إرسال رسائل دورية تلقائية؟",
            parse_mode="Markdown",
            reply_markup=yes_no()
        )
        return STEP_SCHEDULE_CHOICE

async def get_auto_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kw = update.message.text.strip().lower()
    if not kw:
        await update.message.reply_text("⚠️ أرسل كلمة صالحة.")
        return STEP_AUTO_KEYWORD
    context.user_data["keyword"] = kw
    await update.message.reply_text("✅ تم!\n\nأرسل الرد على هذه الكلمة:")
    return STEP_AUTO_REPLY

async def get_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    kw = context.user_data["keyword"]
    store[uid]["auto_replies"][kw] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ تم! لما يكتب أحد `{kw}` سيرد البوت.\n\nتريد إضافة كلمة أخرى؟",
        parse_mode="Markdown",
        reply_markup=yes_no()
    )
    return STEP_AUTO_MORE

async def auto_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "yes":
        await query.edit_message_text("🔍 أرسل الكلمة المفتاحية الجديدة:")
        return STEP_AUTO_KEYWORD
    else:
        await query.edit_message_text(
            "⏰ *جدولة الرسائل*\n\n"
            "هل تريد إرسال رسائل دورية تلقائية؟",
            parse_mode="Markdown",
            reply_markup=yes_no()
        )
        return STEP_SCHEDULE_CHOICE

# ===== دوال الجدولة =====
async def schedule_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "yes":
        await query.edit_message_text(
            "📣 أرسل Chat ID للقناة أو المجموعة:\n\n"
            "للحصول عليه أضف @userinfobot إلى المجموعة وأرسل `/id`"
        )
        return STEP_SCHEDULE_CHAT
    else:
        return await show_summary(update, context)

async def get_schedule_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.text.strip()
    if not (chat_id.startswith("-") or chat_id.isdigit()):
        await update.message.reply_text("⚠️ صيغة Chat ID غير صحيحة. أرسل رقم صحيح (مثل -1001234567890)")
        return STEP_SCHEDULE_CHAT
    context.user_data["chat_id"] = chat_id
    await update.message.reply_text("✅ تم!\n\nأرسل نص الرسالة الدورية:")
    return STEP_SCHEDULE_MSG

async def get_schedule_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text.strip()
    if not msg:
        await update.message.reply_text("⚠️ لا يمكن أن تكون الرسالة فارغة.")
        return STEP_SCHEDULE_MSG
    context.user_data["sch_msg"] = msg
    await update.message.reply_text("⏱ كل كم دقيقة؟ أرسل رقم فقط:")
    return STEP_SCHEDULE_INTERVAL

async def get_schedule_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        interval = int(update.message.text.strip())
        if interval < 1:
            raise ValueError
        store[uid]["schedule"].append({
            "chat_id": context.user_data["chat_id"],
            "message": context.user_data["sch_msg"],
            "interval": interval
        })
        await update.message.reply_text(
            f"✅ تم! رسالة كل {interval} دقيقة.\n\nتريد إضافة جدولة أخرى؟",
            reply_markup=yes_no()
        )
        return STEP_SCHEDULE_CHOICE
    except ValueError:
        await update.message.reply_text("⚠️ أرسل رقم صحيح أكبر من صفر.")
        return STEP_SCHEDULE_INTERVAL

# ===== عرض الملخص =====
async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        uid = query.from_user.id
        sender = query
    else:
        uid = update.effective_user.id
        sender = update.message

    d = store.get(uid)
    if not d:
        await sender.reply_text("⚠️ انتهت الجلسة. ابدأ من جديد بالضغط على /start")
        return ConversationHandler.END

    template_name = TEMPLATES[d["template"]]["name"]

    text = (
        f"📋 *ملخص البوت:*\n\n"
        f"📌 النوع: {template_name}\n"
        f"👋 الترحيب: {d['welcome'][:40]}\n"
    )

    if d["template"] == "simple":
        cmds = "\n".join([f"  • /{k} ← {v}" for k, v in d["commands"].items()]) or "  لا يوجد"
        autos = "\n".join([f"  • '{k}' ← {v}" for k, v in d["auto_replies"].items()]) or "  لا يوجد"
        schs = "\n".join([f"  • كل {s['interval']} دقيقة" for s in d["schedule"]]) or "  لا يوجد"
        text += f"\n⚙️ الأوامر:\n{cmds}\n\n🤖 الردود التلقائية:\n{autos}\n\n⏰ الجدولة:\n{schs}"
    else:
        if d["api_keys"]:
            text += f"\n🔑 مفاتيح API: {', '.join(d['api_keys'].keys())}"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 أنشئ البوت!", callback_data="create")],
        [InlineKeyboardButton("🔄 ابدأ من جديد", callback_data="new_bot")]
    ])

    if update.callback_query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

    return STEP_CONFIRM

# ===== إنشاء حزمة البوت وإرسالها =====
async def create_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    d = store.get(uid)
    if not d:
        await query.edit_message_text("⚠️ بيانات غير موجودة. ابدأ من جديد.")
        return ConversationHandler.END

    await query.edit_message_text("⚙️ جاري بناء حزمة البوت الخاصة بك...")
    try:
        bot_package_data = build_bot_code(d)
        if not bot_package_data:
            raise ValueError("فشل بناء البوت: نوع القالب غير معروف.")
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ في بناء الكود: {e}")
        return ConversationHandler.END

    await package_and_send(update, context, bot_package_data)

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="ماذا تريد أن تفعل بعد ذلك؟",
        reply_markup=main_menu()
    )

    del store[uid]
    return ConversationHandler.END

# ===== دوال بناء الأكواد والقوالب =====
def build_bot_code(d):
    template = d["template"]
    token = d["token"]
    welcome = json.dumps(d["welcome"])

    if template == "simple":
        bot_code = build_simple_bot(d)
        requirements = "python-telegram-bot==20.7\n"
        readme = generate_readme(d, "simple")
    elif template == "downloader":
        bot_code = build_downloader_bot(d)
        requirements = "python-telegram-bot==20.7\nyt-dlp\n"
        readme = generate_readme(d, "downloader")
    elif template == "translator":
        bot_code = build_translator_bot(d)
        requirements = "python-telegram-bot==20.7\ngoogletrans==4.0.0rc1\n"
        readme = generate_readme(d, "translator")
    elif template == "chatgpt":
        bot_code = build_chatgpt_bot(d)
        requirements = "python-telegram-bot==20.7\nopenai\n"
        readme = generate_readme(d, "chatgpt")
    else:
        return None

    return {
        "bot_code": bot_code,
        "requirements": requirements,
        "readme": readme
    }

def generate_readme(d, template_type):
    base = f"""# 🤖 بوت تيليجرام الخاص بك جاهز!

## 📦 محتويات الحزمة
- `bot.py` : الكود المصدري للبوت.
- `requirements.txt` : المكتبات المطلوبة.
- `README.md` : هذا الملف.

## 🚀 كيفية تشغيل البوت على Render (مجاناً 24/7)

1. فك ضغط الملف الذي تلقيته.
2. اذهب إلى [Render.com](https://render.com) وأنشئ حساباً.
3. من لوحة التحكم، اضغط **New +** → **Web Service**.
4. اختر **Upload your own code** وارفع المجلد الذي يحتوي على الملفات.
   - أو ارفع الملفات إلى GitHub واختر **Deploy from GitHub**.
5. في إعدادات الخدمة:
   - **Name**: أي اسم (مثلاً `my-awesome-bot`).
   - **Environment**: `Python 3`.
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Environment Variables**: أضف متغير اسمه `BOT_TOKEN` وقيمته التوكن الخاص بك.
"""
    if template_type == "chatgpt":
        base += f"     - أضف أيضاً `OPENAI_API_KEY` وقيمته: `{d['api_keys'].get('OPENAI_API_KEY', 'YOUR_KEY')}`\n"

    base += """
6. اختر الخطة **Free** واضغط **Create Web Service**.
7. انتظر دقيقتين حتى تكتمل عملية النشر (ستظهر علامة "Live").

## ⏰ الحفاظ على البوت مستيقظاً (عدم التوقف)

لأن الخطة المجانية على Render تجعل الخدمة تنام بعد 15 دقيقة من عدم النشاط، استخدم خدمة **UptimeRobot** المجانية:
- اذهب إلى [UptimeRobot](https://uptimerobot.com/) وأنشئ حساباً.
- أضف مراقب (Monitor) نوعه **HTTP(s)**.
- أدخل رابط تطبيقك الذي يظهر في Render (مثل `https://my-awesome-bot.onrender.com`).
- اضبط الفحص كل **5 دقائق**.

🎉 بهذه الطريقة سيبقى بوتك يعمل 24 ساعة طوال أيام الأسبوع دون توقف!

## ❓ الدعم
إذا واجهت أي مشكلة، تواصل مع صانع البوت.
"""
    return base

def build_simple_bot(d):
    token = d["token"]
    welcome = json.dumps(d["welcome"])
    auto_json = json.dumps(d["auto_replies"], ensure_ascii=False)

    cmd_funcs = ""
    cmd_regs = ""
    for cmd, reply in d["commands"].items():
        safe_cmd = re.sub(r'\W|^(?=\d)', '_', cmd)
        safe_reply = json.dumps(reply)
        cmd_funcs += f'''
async def cmd_{safe_cmd}(update, context):
    await update.message.reply_text({safe_reply})
'''
        cmd_regs += f'    app.add_handler(CommandHandler("{cmd}", cmd_{safe_cmd}))\n'

    sch_code = ""
    for s in d["schedule"]:
        safe_msg = json.dumps(s["message"])
        job_name = f"job_{s['chat_id'].replace('-','').replace('100','')}"
        sch_code += f'''
    async def {job_name}(ctx):
        await ctx.bot.send_message(chat_id="{s['chat_id']}", text={safe_msg})
    app.job_queue.run_repeating({job_name}, interval={s['interval']*60}, first=10)
'''

    return f'''import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "{token}"
AUTO = {auto_json}

async def start(update, context):
    await update.message.reply_text({welcome})

{cmd_funcs}

async def auto_reply(update, context):
    text = update.message.text.lower()
    for kw, rep in AUTO.items():
        if kw in text:
            await update.message.reply_text(rep)
            return

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
{cmd_regs}
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_reply))
{sch_code}
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
'''

def build_downloader_bot(d):
    token = d["token"]
    welcome = json.dumps(d["welcome"])
    return f'''import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

TOKEN = "{token}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text({welcome})

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    await update.message.reply_text("⏳ جاري تحميل الفيديو...")
    try:
        ydl_opts = {{
            'outtmpl': '%(title)s.%(ext)s',
            'quiet': True,
            'format': 'best[height<=720]'
        }}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
        await update.message.reply_video(video=open(filename, 'rb'))
        os.remove(filename)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {{e}}")

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
'''

def build_translator_bot(d):
    token = d["token"]
    welcome = json.dumps(d["welcome"])
    return f'''import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from googletrans import Translator

TOKEN = "{token}"
translator = Translator()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text({welcome})

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        detected = translator.detect(text)
        if detected.lang != 'ar':
            translated = translator.translate(text, dest='ar')
        else:
            translated = translator.translate(text, dest='en')
        await update.message.reply_text(f"🔤 الترجمة:\\n{{translated.text}}")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {{e}}")

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, translate_text))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
'''

def build_chatgpt_bot(d):
    token = d["token"]
    welcome = json.dumps(d["welcome"])
    openai_key = d["api_keys"].get("OPENAI_API_KEY", "")
    return f'''import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai

TOKEN = "{token}"
openai.api_key = "{openai_key}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text({welcome})

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{{"role": "user", "content": user_msg}}]
        )
        reply = response['choices'][0]['message']['content']
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {{e}}")

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
'''

async def package_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_data):
    query = update.callback_query
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
        zip_file.writestr('bot.py', bot_data['bot_code'])
        zip_file.writestr('requirements.txt', bot_data['requirements'])
        zip_file.writestr('README.md', bot_data['readme'])
    zip_buffer.seek(0)

    await query.edit_message_text("✅ تم تجهيز بوتك! جاري إرسال الملفات...")
    await context.bot.send_document(
        chat_id=query.message.chat_id,
        document=zip_buffer,
        filename="my_new_telegram_bot.zip",
        caption="🎁 **حزمة بوتك الجديد جاهزة!**\n\n"
                "افتح الملف `README.md` داخل الأرشيف لتتبع خطوات النشر السهلة.\n"
                "بعد النشر، سيعمل بوتك 24 ساعة دون توقف! 🚀",
        parse_mode="Markdown"
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم الإلغاء.", reply_markup=main_menu())
    uid = update.effective_user.id
    if uid in store:
        del store[uid]
    return ConversationHandler.END

# ===== خادم HTTP وإدارة الإشارات =====
def run_web_server():
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot Factory Running")
        def log_message(self, *args):
            pass

    port = int(os.environ.get("PORT", 8080))
    httpd = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"✅ خادم HTTP يعمل على المنفذ {port}")
    httpd.serve_forever()

async def run_bot():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("❌ BOT_TOKEN غير موجود في متغيرات البيئة!")
        return

    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(new_bot_entry, pattern="^new_bot$")],
        states={
            STEP_TEMPLATE: [CallbackQueryHandler(choose_template, pattern="^tpl_")],
            STEP_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_token)],
            STEP_API_KEYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_api_keys)],
            STEP_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_welcome)],
            STEP_CMD_CHOICE: [CallbackQueryHandler(cmd_choice)],
            STEP_CMD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_cmd_name)],
            STEP_CMD_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_cmd_reply)],
            STEP_CMD_MORE: [CallbackQueryHandler(cmd_more)],
            STEP_AUTO_CHOICE: [CallbackQueryHandler(auto_choice)],
            STEP_AUTO_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_auto_keyword)],
            STEP_AUTO_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_auto_reply)],
            STEP_AUTO_MORE: [CallbackQueryHandler(auto_more)],
            STEP_SCHEDULE_CHOICE: [CallbackQueryHandler(schedule_choice)],
            STEP_SCHEDULE_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_schedule_chat)],
            STEP_SCHEDULE_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_schedule_msg)],
            STEP_SCHEDULE_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_schedule_interval)],
            STEP_CONFIRM: [CallbackQueryHandler(create_bot, pattern="^create$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(show_my_bots, pattern="^my_bots$"))
    app.add_handler(conv_handler)

    print("🚀 Bot Factory يعمل...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def signal_handler():
        print("⚠️ تم استلام إشارة إيقاف، جاري الإغلاق النظيف...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    await stop_event.wait()

    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    print("✅ تم إيقاف البوت بنجاح")

if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()
    asyncio.run(run_bot())