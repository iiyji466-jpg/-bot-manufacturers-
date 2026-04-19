# bot_factory.py - الإصدار النهائي المتوافق مع Docker و Render
import os
import json
import logging
import re
import threading
import subprocess
import sys
import asyncio
import signal
from http.server import HTTPServer, BaseHTTPRequestHandler

# ===== التحقق من إصدار المكتبة =====
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
    STEP_TOKEN, STEP_WELCOME, STEP_CMD_CHOICE, STEP_CMD_NAME,
    STEP_CMD_REPLY, STEP_CMD_MORE, STEP_AUTO_CHOICE, STEP_AUTO_KEYWORD,
    STEP_AUTO_REPLY, STEP_AUTO_MORE, STEP_SCHEDULE_CHOICE, STEP_SCHEDULE_CHAT,
    STEP_SCHEDULE_MSG, STEP_SCHEDULE_INTERVAL, STEP_CONFIRM,
) = range(15)

store = {}

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 صنع بوت جديد", callback_data="new_bot")],
        [InlineKeyboardButton("📋 بوتاتي", callback_data="my_bots")],
    ])

def yes_no():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم", callback_data="yes"),
         InlineKeyboardButton("❌ لا", callback_data="no")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *أهلاً! أنا بوت صانع البوتات*\n\n"
        "بدون كود، أصنع لك بوت Telegram خاص بك!\n\n"
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
        "token": "", "welcome": "", "commands": {},
        "auto_replies": {}, "schedule": []
    }
    await query.edit_message_text(
        "🔑 *الخطوة 1 من 5: توكن البوت*\n\n"
        "افتح @BotFather وأنشئ بوتاً جديداً،\n"
        "ثم أرسل التوكن هنا:\n\n"
        "مثال: `123456789:ABCdef...`",
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
        await update.message.reply_text(
            f"✅ تم! اسم البوت: @{me.username}\n\n"
            "💬 *الخطوة 2 من 5: رسالة الترحيب*\n\n"
            "ما الرسالة التي تظهر عند كتابة /start في بوتك؟",
            parse_mode="Markdown"
        )
        return STEP_WELCOME
    except Exception as e:
        await update.message.reply_text(f"❌ التوكن غير صالح: {e}\nأرسل توكن صحيح:")
        return STEP_TOKEN

async def get_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    store[uid]["welcome"] = update.message.text.strip()
    await update.message.reply_text(
        "✅ تم!\n\n"
        "⚙️ *الخطوة 3 من 5: الأوامر المخصصة*\n\n"
        "هل تريد إضافة أوامر؟\n"
        "مثال: /price يرد بـ 'السعر 50 ريال'",
        parse_mode="Markdown",
        reply_markup=yes_no()
    )
    return STEP_CMD_CHOICE

async def cmd_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "yes":
        await query.edit_message_text("📝 أرسل اسم الأمر بدون / مثل: `price`", parse_mode="Markdown")
        return STEP_CMD_NAME
    else:
        await query.edit_message_text(
            "🤖 *الخطوة 4 من 5: الردود التلقائية*\n\n"
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
            "🤖 *الخطوة 4 من 5: الردود التلقائية*\n\n"
            "هل تريد إضافة ردود تلقائية على كلمات معينة؟",
            parse_mode="Markdown",
            reply_markup=yes_no()
        )
        return STEP_AUTO_CHOICE

async def auto_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "yes":
        await query.edit_message_text("🔍 أرسل الكلمة المفتاحية:\nمثال: `مرحبا`", parse_mode="Markdown")
        return STEP_AUTO_KEYWORD
    else:
        await query.edit_message_text(
            "⏰ *الخطوة 5 من 5: جدولة الرسائل*\n\n"
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
            "⏰ *الخطوة 5 من 5: جدولة الرسائل*\n\n"
            "هل تريد إرسال رسائل دورية تلقائية؟",
            parse_mode="Markdown",
            reply_markup=yes_no()
        )
        return STEP_SCHEDULE_CHOICE

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

    cmds = "\n".join([f"  • /{k} ← {v}" for k, v in d["commands"].items()]) or "  لا يوجد"
    autos = "\n".join([f"  • '{k}' ← {v}" for k, v in d["auto_replies"].items()]) or "  لا يوجد"
    schs = "\n".join([f"  • كل {s['interval']} دقيقة ← {s['message'][:20]}..." for s in d["schedule"]]) or "  لا يوجد"

    text = (
        "📋 *ملخص البوت:*\n\n"
        f"👋 الترحيب: {d['welcome'][:40]}\n\n"
        f"⚙️ الأوامر:\n{cmds}\n\n"
        f"🤖 الردود التلقائية:\n{autos}\n\n"
        f"⏰ الجدولة:\n{schs}"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 أنشئ البوت!", callback_data="create")],
        [InlineKeyboardButton("🔄 ابدأ من جديد", callback_data="new_bot")]
    ])

    if update.callback_query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

    return STEP_CONFIRM

async def create_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    d = store.get(uid)
    if not d:
        await query.edit_message_text("⚠️ بيانات غير موجودة. ابدأ من جديد.")
        return ConversationHandler.END

    await query.edit_message_text("⚙️ جاري بناء البوت...")
    try:
        code = build_bot_code(d)
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ في بناء الكود: {e}")
        return ConversationHandler.END

    base_dir = os.getcwd()
    bots_dir = os.path.join(base_dir, "bots")
    os.makedirs(bots_dir, exist_ok=True)

    short = d["token"].split(":")[0]
    filename = os.path.join(bots_dir, f"bot_{short}.py")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)

    try:
        subprocess.Popen(
            [sys.executable, filename],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            cwd=base_dir
        )
    except Exception as e:
        await query.edit_message_text(f"❌ فشل تشغيل البوت: {e}")
        return ConversationHandler.END

    await query.edit_message_text(
        "🎉 *تم إنشاء بوتك بنجاح!*\n\n"
        "✅ البوت يعمل الآن\n"
        "افتح بوتك على Telegram واكتب /start",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )
    del store[uid]
    return ConversationHandler.END

def build_bot_code(d):
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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم الإلغاء.", reply_markup=main_menu())
    uid = update.effective_user.id
    if uid in store:
        del store[uid]
    return ConversationHandler.END

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
            STEP_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_token)],
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

    # تشغيل البوت بشكل متحكم به لاستقبال إشارات الإنهاء
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # انتظار إشارة الإيقاف (SIGTERM من Render)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def signal_handler():
        print("⚠️ تم استلام إشارة إيقاف، جاري الإغلاق النظيف...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # على بعض الأنظمة (مثل Windows) قد لا تكون add_signal_handler مدعومة
            pass

    await stop_event.wait()

    # إيقاف البوت بشكل آمن
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    print("✅ تم إيقاف البوت بنجاح")

if __name__ == "__main__":
    # تشغيل خادم HTTP في thread منفصل لمنع Render من إيقاف الخدمة
    threading.Thread(target=run_web_server, daemon=True).start()
    # تشغيل البوت مع التعامل الكامل مع الإشارات
    asyncio.run(run_bot())