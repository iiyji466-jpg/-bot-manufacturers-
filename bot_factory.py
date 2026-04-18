import logging
import json
import os
import subprocess
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== مراحل المحادثة =====
(
    ASK_TOKEN,
    ASK_WELCOME,
    ASK_COMMANDS_CHOICE,
    ASK_COMMAND_NAME,
    ASK_COMMAND_REPLY,
    ASK_MORE_COMMANDS,
    ASK_AUTO_REPLY_CHOICE,
    ASK_AUTO_KEYWORD,
    ASK_AUTO_RESPONSE,
    ASK_MORE_AUTO,
    ASK_SCHEDULE_CHOICE,
    ASK_SCHEDULE_CHAT_ID,
    ASK_SCHEDULE_MESSAGE,
    ASK_SCHEDULE_INTERVAL,
    CONFIRM,
) = range(15)

# ===== تخزين بيانات كل مستخدم مؤقتاً =====
user_data_store = {}


def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 صنع بوت جديد", callback_data="new_bot")],
        [InlineKeyboardButton("📋 بوتاتي", callback_data="my_bots")],
    ])


def yes_no_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم", callback_data="yes"),
         InlineKeyboardButton("❌ لا", callback_data="no")]
    ])


# ===== /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *أهلاً! أنا بوت صانع البوتات*\n\n"
        "أقدر أساعدك تصنع بوت Telegram خاص بك بدون كود!\n\n"
        "اختر من القائمة:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


# ===== زر صنع بوت جديد =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "new_bot":
        user_data_store[user_id] = {
            "token": "",
            "welcome": "",
            "commands": {},
            "auto_replies": {},
            "schedule": []
        }
        await query.edit_message_text(
            "🔑 *الخطوة 1: توكن البوت*\n\n"
            "روح لـ @BotFather وصنع بوت جديد، ثم أرسل لي التوكن هنا:\n\n"
            "مثال: `123456:ABCdef...`",
            parse_mode="Markdown"
        )
        return ASK_TOKEN

    elif query.data == "my_bots":
        bots_dir = "bots"
        if not os.path.exists(bots_dir) or not os.listdir(bots_dir):
            await query.edit_message_text(
                "📭 ما عندك بوتات بعد!\n\nاضغط /start لتصنع بوت.",
            )
        else:
            bots = os.listdir(bots_dir)
            text = "📋 *بوتاتك:*\n\n" + "\n".join([f"• `{b}`" for b in bots])
            await query.edit_message_text(text, parse_mode="Markdown")


# ===== استقبال التوكن =====
async def receive_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    token = update.message.text.strip()

    if ":" not in token or len(token) < 20:
        await update.message.reply_text(
            "⚠️ التوكن يبدو غلط. تأكد منه وأعد الإرسال."
        )
        return ASK_TOKEN

    user_data_store[user_id]["token"] = token

    await update.message.reply_text(
        "✅ تم حفظ التوكن!\n\n"
        "💬 *الخطوة 2: رسالة الترحيب*\n\n"
        "أرسل الرسالة اللي تظهر للمستخدم لما يكتب /start في بوتك:",
        parse_mode="Markdown"
    )
    return ASK_WELCOME


# ===== استقبال رسالة الترحيب =====
async def receive_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id]["welcome"] = update.message.text.strip()

    await update.message.reply_text(
        "✅ تم!\n\n"
        "⚙️ *الخطوة 3: الأوامر المخصصة*\n\n"
        "تريد تضيف أوامر مخصصة لبوتك؟\n"
        "مثال: /price يرد بـ 'السعر 100 ريال'",
        reply_markup=yes_no_keyboard()
    )
    return ASK_COMMANDS_CHOICE


# ===== اختيار إضافة أوامر =====
async def commands_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "yes":
        await query.edit_message_text(
            "📝 *اسم الأمر*\n\nأرسل اسم الأمر بدون / مثل: `price` أو `info`",
            parse_mode="Markdown"
        )
        return ASK_COMMAND_NAME
    else:
        await query.edit_message_text(
            "💬 *الخطوة 4: الردود التلقائية*\n\n"
            "تريد تضيف ردود تلقائية على كلمات معينة؟\n"
            "مثال: لو قال 'مرحبا' يرد البوت بـ 'أهلاً!'",
            reply_markup=yes_no_keyboard()
        )
        return ASK_AUTO_REPLY_CHOICE


# ===== استقبال اسم الأمر =====
async def receive_command_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cmd = update.message.text.strip().replace("/", "").lower()
    context.user_data["current_cmd"] = cmd

    await update.message.reply_text(
        f"✅ الأمر: `/{cmd}`\n\nأرسل الرد اللي يظهر لما يكتب المستخدم هذا الأمر:",
        parse_mode="Markdown"
    )
    return ASK_COMMAND_REPLY


# ===== استقبال رد الأمر =====
async def receive_command_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cmd = context.user_data.get("current_cmd")
    reply = update.message.text.strip()
    user_data_store[user_id]["commands"][cmd] = reply

    await update.message.reply_text(
        f"✅ تم حفظ الأمر `/{cmd}`!\n\nتريد تضيف أمر آخر؟",
        parse_mode="Markdown",
        reply_markup=yes_no_keyboard()
    )
    return ASK_MORE_COMMANDS


# ===== المزيد من الأوامر =====
async def more_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "yes":
        await query.edit_message_text(
            "📝 أرسل اسم الأمر الجديد:",
        )
        return ASK_COMMAND_NAME
    else:
        await query.edit_message_text(
            "💬 *الخطوة 4: الردود التلقائية*\n\n"
            "تريد تضيف ردود تلقائية على كلمات معينة؟",
            parse_mode="Markdown",
            reply_markup=yes_no_keyboard()
        )
        return ASK_AUTO_REPLY_CHOICE


# ===== اختيار ردود تلقائية =====
async def auto_reply_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "yes":
        await query.edit_message_text(
            "🔍 أرسل الكلمة أو الجملة اللي تريد البوت يكشفها:\n"
            "مثال: `مرحبا`",
            parse_mode="Markdown"
        )
        return ASK_AUTO_KEYWORD
    else:
        await query.edit_message_text(
            "⏰ *الخطوة 5: جدولة الرسائل*\n\n"
            "تريد البوت يرسل رسائل تلقائية بشكل دوري؟",
            reply_markup=yes_no_keyboard()
        )
        return ASK_SCHEDULE_CHOICE


# ===== استقبال الكلمة المفتاحية =====
async def receive_auto_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["current_keyword"] = update.message.text.strip().lower()
    await update.message.reply_text("✅ الكلمة المفتاحية محفوظة!\n\nأرسل الرد على هذه الكلمة:")
    return ASK_AUTO_RESPONSE


# ===== استقبال الرد التلقائي =====
async def receive_auto_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyword = context.user_data.get("current_keyword")
    response = update.message.text.strip()
    user_data_store[user_id]["auto_replies"][keyword] = response

    await update.message.reply_text(
        f"✅ تم! لما يقول أحد `{keyword}` سيرد البوت تلقائياً.\n\nتريد تضيف كلمة أخرى؟",
        reply_markup=yes_no_keyboard()
    )
    return ASK_MORE_AUTO


# ===== المزيد من الردود التلقائية =====
async def more_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "yes":
        await query.edit_message_text("🔍 أرسل الكلمة المفتاحية الجديدة:")
        return ASK_AUTO_KEYWORD
    else:
        await query.edit_message_text(
            "⏰ *الخطوة 5: جدولة الرسائل*\n\n"
            "تريد البوت يرسل رسائل تلقائية بشكل دوري لقناة أو مجموعة؟",
            parse_mode="Markdown",
            reply_markup=yes_no_keyboard()
        )
        return ASK_SCHEDULE_CHOICE


# ===== اختيار الجدولة =====
async def schedule_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "yes":
        await query.edit_message_text(
            "📣 أرسل Chat ID للقناة أو المجموعة:\n\n"
            "للحصول عليه: أضف @userinfobot للمجموعة أو القناة وسيعطيك الـ ID"
        )
        return ASK_SCHEDULE_CHAT_ID
    else:
        return await show_summary(update, context)


# ===== استقبال Chat ID =====
async def receive_schedule_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["schedule_chat_id"] = update.message.text.strip()
    await update.message.reply_text("✅ تم!\n\nأرسل نص الرسالة الدورية:")
    return ASK_SCHEDULE_MESSAGE


# ===== استقبال نص الرسالة الدورية =====
async def receive_schedule_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["schedule_message"] = update.message.text.strip()
    await update.message.reply_text(
        "⏱ كل كم دقيقة تريد إرسال الرسالة؟\n"
        "أرسل رقم فقط (مثال: 60 لكل ساعة):"
    )
    return ASK_SCHEDULE_INTERVAL


# ===== استقبال الفترة الزمنية =====
async def receive_schedule_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        interval = int(update.message.text.strip())
        user_data_store[user_id]["schedule"].append({
            "chat_id": context.user_data["schedule_chat_id"],
            "message": context.user_data["schedule_message"],
            "interval_minutes": interval
        })
        await update.message.reply_text(f"✅ تم ضبط الجدولة كل {interval} دقيقة!")
    except ValueError:
        await update.message.reply_text("⚠️ أرسل رقم صحيح فقط.")
        return ASK_SCHEDULE_INTERVAL

    return await show_summary(update, context)


# ===== عرض الملخص =====
async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data_store[user_id]

    cmds_text = "\n".join([f"  • /{k} ← {v}" for k, v in data["commands"].items()]) or "  لا يوجد"
    auto_text = "\n".join([f"  • '{k}' ← {v}" for k, v in data["auto_replies"].items()]) or "  لا يوجد"
    schedule_text = "\n".join([f"  • كل {s['interval_minutes']} دقيقة في {s['chat_id']}" for s in data["schedule"]]) or "  لا يوجد"

    summary = (
        "📋 *ملخص البوت الجديد:*\n\n"
        f"🔑 التوكن: `{data['token'][:10]}...`\n"
        f"👋 رسالة الترحيب: {data['welcome'][:50]}\n\n"
        f"⚙️ الأوامر:\n{cmds_text}\n\n"
        f"🤖 الردود التلقائية:\n{auto_text}\n\n"
        f"⏰ الجدولة:\n{schedule_text}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 صنع البوت!", callback_data="create_bot")],
        [InlineKeyboardButton("🔄 ابدأ من جديد", callback_data="new_bot")]
    ])

    if update.callback_query:
        await update.callback_query.edit_message_text(summary, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=keyboard)

    return CONFIRM


# ===== إنشاء البوت =====
async def create_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = user_data_store[user_id]

    await query.edit_message_text("⚙️ جاري بناء البوت...")

    # توليد الكود
    bot_code = generate_bot_code(data)

    # حفظ الكود
    os.makedirs("bots", exist_ok=True)
    bot_token_short = data["token"].split(":")[0]
    filename = f"bots/bot_{bot_token_short}.py"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(bot_code)

    # تشغيل البوت في الخلفية
    subprocess.Popen(
        [sys.executable, filename],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    await query.edit_message_text(
        f"🎉 *تم صنع بوتك بنجاح!*\n\n"
        f"✅ البوت شغّال الآن في الخلفية\n"
        f"📁 الملف: `{filename}`\n\n"
        f"اذهب لبوتك على Telegram وجرّبه! 🚀",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END


# ===== توليد كود البوت الجديد =====
def generate_bot_code(data: dict) -> str:
    token = data["token"]
    welcome = data["welcome"].replace('"', '\\"')
    commands = data["commands"]
    auto_replies = data["auto_replies"]
    schedule = data["schedule"]

    # بناء handlers الأوامر
    command_handlers_code = ""
    command_register_code = ""
    for cmd, reply in commands.items():
        reply_escaped = reply.replace('"', '\\"')
        command_handlers_code += f'''
async def cmd_{cmd}(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("{reply_escaped}")
'''
        command_register_code += f'    app.add_handler(CommandHandler("{cmd}", cmd_{cmd}))\n'

    # بناء الردود التلقائية
    auto_replies_json = json.dumps(auto_replies, ensure_ascii=False)

    # بناء jobs الجدولة
    schedule_code = ""
    for s in schedule:
        msg = s["message"].replace('"', '\\"')
        schedule_code += f'''
    context.job_queue.run_repeating(
        lambda ctx: ctx.bot.send_message(chat_id="{s["chat_id"]}", text="{msg}"),
        interval={s["interval_minutes"] * 60},
        first=10
    )
'''

    code = f'''import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)

TOKEN = "{token}"
AUTO_REPLIES = {auto_replies_json}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("{welcome}")

{command_handlers_code}

async def auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    for keyword, response in AUTO_REPLIES.items():
        if keyword in text:
            await update.message.reply_text(response)
            return

async def main():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading, os

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running")
        def log_message(self, *args): pass

    def run_server():
        port = int(os.environ.get("PORT", 8080))
        HTTPServer(("0.0.0.0", port), Handler).serve_forever()

    threading.Thread(target=run_server, daemon=True).start()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
{command_register_code}
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_reply))
{schedule_code}
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
'''
    return code


# ===== الإلغاء =====
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم الإلغاء.", reply_markup=get_main_keyboard())
    return ConversationHandler.END


# ===== التشغيل الرئيسي =====
def main():
    import os
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot Factory Running")
        def log_message(self, *args): pass

    def run_server():
        port = int(os.environ.get("PORT", 8080))
        HTTPServer(("0.0.0.0", port), Handler).serve_forever()

    threading.Thread(target=run_server, daemon=True).start()

    TOKEN = "8297443710:AAHDZseyv5jwjrSzjc1AEvAkXM1nLPAfRrQ"

    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^new_bot$")],
        states={
            ASK_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_token)],
            ASK_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_welcome)],
            ASK_COMMANDS_CHOICE: [CallbackQueryHandler(commands_choice)],
            ASK_COMMAND_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_command_name)],
            ASK_COMMAND_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_command_reply)],
            ASK_MORE_COMMANDS: [CallbackQueryHandler(more_commands)],
            ASK_AUTO_REPLY_CHOICE: [CallbackQueryHandler(auto_reply_choice)],
            ASK_AUTO_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_auto_keyword)],
            ASK_AUTO_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_auto_response)],
            ASK_MORE_AUTO: [CallbackQueryHandler(more_auto)],
            ASK_SCHEDULE_CHOICE: [CallbackQueryHandler(schedule_choice)],
            ASK_SCHEDULE_CHAT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_schedule_chat_id)],
            ASK_SCHEDULE_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_schedule_message)],
            ASK_SCHEDULE_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_schedule_interval)],
            CONFIRM: [CallbackQueryHandler(create_bot, pattern="^create_bot$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(conv)

    print("🚀 Bot Factory is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
