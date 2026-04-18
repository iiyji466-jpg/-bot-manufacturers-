import os
import json
import logging
import threading
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
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
    STEP_CONFIRM,
) = range(15)

store = {}

# ===== القوائم =====
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

# ===== start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً! أنا صانع بوتات تيليجرام\n\nاختر:",
        reply_markup=main_menu()
    )

# ===== القائمة =====
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if query.data == "new_bot":
        store[uid] = {
            "token": "",
            "welcome": "",
            "commands": {},
            "auto_replies": {},
            "schedule": []
        }
        await query.edit_message_text(
            "🔑 أرسل توكن البوت من BotFather:"
        )
        return STEP_TOKEN

    elif query.data == "my_bots":
        bots_dir = "bots"
        if not os.path.exists(bots_dir):
            await query.edit_message_text("📭 لا يوجد بوتات")
        else:
            bots = os.listdir(bots_dir)
            await query.edit_message_text("\n".join(bots) or "فارغ")

# ===== التوكن =====
async def get_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    token = update.message.text.strip()

    if ":" not in token or len(token) < 40:
        await update.message.reply_text("⚠️ توكن غير صحيح")
        return STEP_TOKEN

    store[uid]["token"] = token
    await update.message.reply_text("💬 أرسل رسالة الترحيب:")
    return STEP_WELCOME

# ===== الترحيب =====
async def get_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    store[uid]["welcome"] = update.message.text.strip()

    await update.message.reply_text(
        "⚙️ هل تريد أوامر مخصصة؟",
        reply_markup=yes_no()
    )
    return STEP_CMD_CHOICE

# ===== الأوامر =====
async def cmd_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "yes":
        await q.edit_message_text("أرسل اسم الأمر بدون /")
        return STEP_CMD_NAME
    else:
        return await auto_choice(update, context)

async def get_cmd_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.strip().replace("/", "").lower()
    context.user_data["cmd"] = cmd
    await update.message.reply_text("أرسل الرد:")
    return STEP_CMD_REPLY

async def get_cmd_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cmd = context.user_data["cmd"]

    store[uid]["commands"][cmd] = update.message.text.strip()

    await update.message.reply_text("هل تريد أمر آخر؟", reply_markup=yes_no())
    return STEP_CMD_MORE

async def cmd_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "yes":
        await q.edit_message_text("أرسل اسم الأمر:")
        return STEP_CMD_NAME
    else:
        return await auto_choice(update, context)

# ===== الردود التلقائية =====
async def auto_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "yes":
        await q.edit_message_text("أرسل الكلمة:")
        return STEP_AUTO_KEYWORD
    else:
        return await schedule_choice(update, context)

async def get_auto_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["keyword"] = update.message.text.lower().strip()
    await update.message.reply_text("أرسل الرد:")
    return STEP_AUTO_REPLY

async def get_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    kw = context.user_data["keyword"]

    store[uid]["auto_replies"][kw] = update.message.text.strip()

    await update.message.reply_text("هل تضيف كلمة أخرى؟", reply_markup=yes_no())
    return STEP_AUTO_MORE

async def auto_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "yes":
        await q.edit_message_text("أرسل الكلمة:")
        return STEP_AUTO_KEYWORD
    else:
        return await schedule_choice(update, context)

# ===== الجدولة =====
async def schedule_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "yes":
        await q.edit_message_text("أرسل Chat ID:")
        return STEP_SCHEDULE_CHAT
    else:
        return await show_summary(update, context)

async def get_schedule_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["chat_id"] = update.message.text.strip()
    await update.message.reply_text("أرسل الرسالة:")
    return STEP_SCHEDULE_MSG

async def get_schedule_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sch_msg"] = update.message.text.strip()
    await update.message.reply_text("كل كم دقيقة؟")
    return STEP_SCHEDULE_INTERVAL

async def get_schedule_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    try:
        interval = int(update.message.text.strip())
        if interval <= 0:
            raise ValueError

        store[uid]["schedule"].append({
            "chat_id": context.user_data["chat_id"],
            "message": context.user_data["sch_msg"],
            "interval": interval
        })

        await update.message.reply_text("تم الحفظ")

    except:
        await update.message.reply_text("رقم غير صحيح")
        return STEP_SCHEDULE_INTERVAL

    return await show_summary(update, context)

# ===== الملخص =====
async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    d = store[uid]

    text = f"""
📋 الملخص:

👋 {d['welcome']}
⚙️ أوامر: {len(d['commands'])}
🤖 ردود: {len(d['auto_replies'])}
⏰ جدولة: {len(d['schedule'])}
"""

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 إنشاء", callback_data="create")]
    ])

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)

    return STEP_CONFIRM

# ===== إنشاء البوت =====
async def create_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    data = store[uid]

    os.makedirs("bots", exist_ok=True)

    code = build_bot_code(data)
    path = f"bots/bot_{uid}.py"

    with open(path, "w", encoding="utf-8") as f:
        f.write(code)

    subprocess.Popen(
        [sys.executable, path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    await q.edit_message_text("✅ تم تشغيل البوت")
    return ConversationHandler.END

# ===== بناء كود البوت =====
def build_bot_code(d):
    token = d["token"]
    welcome = d["welcome"].replace('"', '\\"')
    auto = json.dumps(d["auto_replies"], ensure_ascii=False)

    return f'''
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "{token}"
AUTO = {auto}

async def start(update, context):
    await update.message.reply_text("{welcome}")

async def auto(update, context):
    if not update.message:
        return
    text = update.message.text.lower()
    for k, v in AUTO.items():
        if text == k:
            await update.message.reply_text(v)

app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto))

print("Bot running...")
app.run_polling()
'''

# ===== التشغيل =====
def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("BOT_TOKEN missing")
        return

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern="new_bot")],
        states={
            STEP_TOKEN: [MessageHandler(filters.TEXT, get_token)],
            STEP_WELCOME: [MessageHandler(filters.TEXT, get_welcome)],
            STEP_CMD_CHOICE: [CallbackQueryHandler(cmd_choice)],
            STEP_CMD_NAME: [MessageHandler(filters.TEXT, get_cmd_name)],
            STEP_CMD_REPLY: [MessageHandler(filters.TEXT, get_cmd_reply)],
            STEP_CMD_MORE: [CallbackQueryHandler(cmd_more)],
            STEP_AUTO_KEYWORD: [MessageHandler(filters.TEXT, get_auto_keyword)],
            STEP_AUTO_REPLY: [MessageHandler(filters.TEXT, get_auto_reply)],
            STEP_AUTO_MORE: [CallbackQueryHandler(auto_more)],
            STEP_SCHEDULE_CHAT: [MessageHandler(filters.TEXT, get_schedule_chat)],
            STEP_SCHEDULE_MSG: [MessageHandler(filters.TEXT, get_schedule_msg)],
            STEP_SCHEDULE_INTERVAL: [MessageHandler(filters.TEXT, get_schedule_interval)],
            STEP_CONFIRM: [CallbackQueryHandler(create_bot, pattern="create")],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    print("Running...")
    app.run_polling()

if __name__ == "__main__":
    main()