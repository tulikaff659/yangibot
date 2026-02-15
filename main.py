import os
import logging
import asyncio
from typing import Set, Dict, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
    CallbackContext,
)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
BROADCAST_MSG, ASK_BUTTON, BUTTON_TEXT, BUTTON_URL = range(4)
APK_WAIT = 4  # for /setapk
LINK_WAIT_TEXT, LINK_WAIT_URL = 5, 6

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

missing_vars = []
if not BOT_TOKEN:
    missing_vars.append("BOT_TOKEN")
if not ADMIN_ID:
    missing_vars.append("ADMIN_ID")
try:
    ADMIN_ID = int(ADMIN_ID) if ADMIN_ID else None
except ValueError:
    missing_vars.append("ADMIN_ID (integer bo‘lishi kerak)")

if missing_vars:
    raise ValueError(f"Kerakli o‘zgaruvchilar topilmadi: {', '.join(missing_vars)}")

# Xotirada ma'lumotlar
users: Set[int] = set()
settings: Dict[str, str] = {
    "apk_enabled": "false",
    "apk_file_id": "",
    "apk_caption": "📥 APK yuklash",
    "link_text": "",
    "link_url": "",
}

def add_user(user_id: int):
    users.add(user_id)

def get_user_count() -> int:
    return len(users)

def get_all_users() -> list[int]:
    return list(users)

def get_setting(key: str) -> str:
    return settings.get(key, "")

def set_setting(key: str, value: str):
    settings[key] = value

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID

# ------------------- /start (chiroyli xabar) -------------------
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    add_user(user.id)

    text = (
        "✨ *Betwinner rasmiy botiga xush kelibsiz!* ✨\n\n"
        "📱 Endi Telegramdan *chiqmagan holda* bets larni amalga oshirishingiz mumkin.\n"
        "🔽 Quyidagi tugmalardan birini tanlang:\n\n"
        "⚡️ *BetsPlay* – tezkor sahifaga o‘tish\n"
        "📦 *APK yuklash* – so‘nggi versiyani yuklash\n\n"
        "🎯 *Foydalanuvchilarga qulaylik* – bu bizning asosiy maqsadimiz!\n"
        "💬 Savol va takliflar uchun @admin ga murojaat qiling."
    )

    keyboard = []

    # Havola tugmasi (agar o‘rnatilgan bo‘lsa)
    link_text = get_setting("link_text")
    link_url = get_setting("link_url")
    if link_text and link_url:
        keyboard.append([InlineKeyboardButton(link_text, url=link_url)])

    # APK tugmasi (agar yoqilgan va fayl mavjud bo‘lsa)
    apk_enabled = get_setting("apk_enabled") == "true"
    apk_file_id = get_setting("apk_file_id")
    if apk_enabled and apk_file_id:
        apk_caption = get_setting("apk_caption") or "📥 APK yuklash"
        keyboard.append([InlineKeyboardButton(apk_caption, callback_data="download_apk")])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

# ------------------- APK yuklash tugmasi bosilganda -------------------
async def download_apk(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    apk_file_id = get_setting("apk_file_id")
    if not apk_file_id:
        await query.edit_message_text("❌ APK fayli topilmadi.")
        return

    # Faylni yuborish
    await query.message.reply_document(document=apk_file_id, caption="📦 Betwinner APK")

# ------------------- Admin buyruqlari -------------------
async def users_count(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    count = get_user_count()
    await update.message.reply_text(f"👥 Foydalanuvchilar soni: {count}")

async def toggle_apk(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    current = get_setting("apk_enabled")
    new = "false" if current == "true" else "true"
    set_setting("apk_enabled", new)
    status = "yoqildi ✅" if new == "true" else "o‘chirildi ❌"
    await update.message.reply_text(f"APK tugmasi {status}.")

# ------------------- /setapk (APK faylini yuklash) -------------------
async def setapk_start(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📤 Endi APK faylini (document sifatida) yuboring.\n"
        "Ixtiyoriy ravishda caption (tugma matni) yozishingiz mumkin.\n"
        "Bekor qilish uchun /cancel."
    )
    return APK_WAIT

async def setapk_receive(update: Update, context: CallbackContext):
    if not update.message.document:
        await update.message.reply_text("❌ Iltimos, faylni document sifatida yuboring.")
        return APK_WAIT

    file_id = update.message.document.file_id
    caption = update.message.caption or "📥 APK yuklash"  # agar caption bo‘lmasa, default

    set_setting("apk_file_id", file_id)
    set_setting("apk_caption", caption)

    await update.message.reply_text(f"✅ APK fayli saqlandi!\nTugma matni: {caption}")
    return ConversationHandler.END

# ------------------- /setlink (havola tugmasini o‘rnatish) -------------------
async def setlink_start(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🔗 Endi tugma matnini yuboring (masalan: *BetsPlay*).\n"
        "Bekor qilish uchun /cancel.",
        parse_mode="Markdown"
    )
    return LINK_WAIT_TEXT

async def setlink_text(update: Update, context: CallbackContext):
    context.user_data['link_text'] = update.message.text
    await update.message.reply_text("🌐 Endi URL manzilini yuboring (masalan: https://example.com).")
    return LINK_WAIT_URL

async def setlink_url(update: Update, context: CallbackContext):
    url = update.message.text
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ URL 'http://' yoki 'https://' bilan boshlanishi kerak. Qaytadan urinib ko‘ring.")
        return LINK_WAIT_URL

    text = context.user_data.get('link_text', 'Batafsil')
    set_setting("link_text", text)
    set_setting("link_url", url)

    await update.message.reply_text(f"✅ Havola tugmasi saqlandi:\nMatn: {text}\nURL: {url}")
    context.user_data.clear()
    return ConversationHandler.END

# ------------------- Broadcast (tugma qo‘shish imkoniyati bilan) -------------------
async def broadcast_start(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📨 Endi barcha foydalanuvchilarga yubormoqchi bo‘lgan xabaringizni yuboring.\n"
        "(Matn, rasm, video, hujjat – istalgan formatda)\n"
        "Bekor qilish uchun /cancel yuboring."
    )
    return BROADCAST_MSG

async def broadcast_receive(update: Update, context: CallbackContext):
    context.user_data['broadcast_message'] = update.message
    keyboard = [
        [InlineKeyboardButton("➕ Tugma qo‘shish", callback_data="add_btn")],
        [InlineKeyboardButton("❌ Tugmasiz yuborish", callback_data="no_btn")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Ushbu xabarga tugma qo‘shishni xohlaysizmi?",
        reply_markup=reply_markup
    )
    return ASK_BUTTON

async def button_choice(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == "add_btn":
        await query.edit_message_text("Tugma matnini yuboring:")
        return BUTTON_TEXT
    else:
        await send_broadcast(query, context, None)
        return ConversationHandler.END

async def button_text(update: Update, context: CallbackContext):
    context.user_data['btn_text'] = update.message.text
    await update.message.reply_text(
        "Tugma URL manzilini yuboring.\n"
        "Agar *APK yuklash* tugmasi bo‘lishini istasangiz /skip yuboring."
    )
    return BUTTON_URL

async def button_url(update: Update, context: CallbackContext):
    text = update.message.text
    apk_file_id = get_setting("apk_file_id")
    if text == "/skip" and apk_file_id:
        # APK tugmasi – callback_data bilan
        button = InlineKeyboardButton(context.user_data['btn_text'], callback_data="download_apk")
    else:
        # Oddiy URL tugma
        if not text.startswith(('http://', 'https://')):
            await update.message.reply_text("❌ URL noto‘g‘ri. Qaytadan urinib ko‘ring.")
            return BUTTON_URL
        button = InlineKeyboardButton(context.user_data['btn_text'], url=text)

    await send_broadcast(update, context, button)
    return ConversationHandler.END

async def send_broadcast(update_or_query, context: CallbackContext, button=None):
    msg = context.user_data.get('broadcast_message')
    if not msg:
        await (update_or_query.message.reply_text("Xatolik: xabar topilmadi."))
        return

    users_list = get_all_users()
    sent = failed = 0
    reply_markup = InlineKeyboardMarkup([[button]]) if button else None

    await (update_or_query.message.reply_text(
        f"⏳ Xabar {len(users_list)} ta foydalanuvchiga yuborilmoqda..."
    ))

    for uid in users_list:
        try:
            await msg.copy(chat_id=uid, reply_markup=reply_markup)
            sent += 1
        except Exception as e:
            logger.warning(f"Yuborilmadi {uid}: {e}")
            failed += 1
        await asyncio.sleep(0.05)

    await (update_or_query.message.reply_text(
        f"✅ Yuborildi: {sent}\n❌ Xatolik: {failed}"
    ))
    context.user_data.clear()

async def broadcast_cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("🚫 Broadcast bekor qilindi.")
    context.user_data.clear()
    return ConversationHandler.END

# ------------------- Noma'lum buyruqlar -------------------
async def unknown(update: Update, context: CallbackContext):
    await update.message.reply_text("❓ Tushunarsiz buyruq.")

# ------------------- Asosiy -------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Oddiy handlerlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("users", users_count))
    app.add_handler(CommandHandler("toggle_apk", toggle_apk))
    app.add_handler(CallbackQueryHandler(download_apk, pattern="^download_apk$"))

    # /setapk conversation
    setapk_conv = ConversationHandler(
        entry_points=[CommandHandler("setapk", setapk_start)],
        states={
            APK_WAIT: [MessageHandler(filters.Document.ALL, setapk_receive)]
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],  # reuse cancel
    )
    app.add_handler(setapk_conv)

    # /setlink conversation
    setlink_conv = ConversationHandler(
        entry_points=[CommandHandler("setlink", setlink_start)],
        states={
            LINK_WAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setlink_text)],
            LINK_WAIT_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, setlink_url)],
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    app.add_handler(setlink_conv)

    # Broadcast conversation
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_receive)],
            ASK_BUTTON: [CallbackQueryHandler(button_choice)],
            BUTTON_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, button_text)],
            BUTTON_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, button_url)],
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    app.add_handler(broadcast_conv)

    # Noma'lum buyruqlar
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    app.run_polling()

if __name__ == "__main__":
    main()
