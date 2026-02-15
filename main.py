import os
import logging
import asyncio
from typing import Set, Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackContext,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BROADCAST_MSG = 1

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
APK_LINK = os.getenv("APK_LINK", "https://example.com/app.apk")

missing_vars = []
if not BOT_TOKEN:
    missing_vars.append("BOT_TOKEN")
if not ADMIN_ID:
    missing_vars.append("ADMIN_ID")
try:
    ADMIN_ID = int(ADMIN_ID) if ADMIN_ID else None
except ValueError:
    missing_vars.append("ADMIN_ID (integer boʻlishi kerak)")

if missing_vars:
    raise ValueError(f"Kerakli oʻzgaruvchilar topilmadi: {', '.join(missing_vars)}")

# Xotirada saqlash
user_set: Set[int] = set()
settings: Dict[str, str] = {"apk_enabled": "false"}

def add_user(user_id: int):
    user_set.add(user_id)

def get_user_count() -> int:
    return len(user_set)

def get_all_users() -> list[int]:
    return list(user_set)

def get_setting(key: str) -> str:
    return settings.get(key, "false")

def set_setting(key: str, value: str):
    settings[key] = value

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID

async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    add_user(user.id)

    text = (
        "🌟 *Betwinner rasmiy boti* 🌟\n\n"
        "Endi Telegramdan chiqmagan holda *betslarni amalga oshirishingiz mumkin*.\n"
        "Ekran pastki qismidagi *BetsPlay* tugmasini bosib Betwinner sahifasiga oʻting va "
        "betslarni amalga oshiring.\n\n"
        "Foydalanuvchilarga qulaylik tilagan holda, *Betwinner*! 🎉"
    )

    keyboard = []
    if get_setting("apk_enabled") == "true":
        keyboard.append([InlineKeyboardButton("📥 APK yuklash", url=APK_LINK)])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def users_command(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    await update.message.reply_text(f"👥 Foydalanuvchilar soni: {get_user_count()}")

async def toggle_apk(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    current = get_setting("apk_enabled")
    new = "false" if current == "true" else "true"
    set_setting("apk_enabled", new)
    status = "yoqildi ✅" if new == "true" else "oʻchirildi ❌"
    await update.message.reply_text(f"APK tugmasi {status}.")

async def broadcast_start(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📨 Endi barcha foydalanuvchilarga yubormoqchi boʻlgan xabaringizni yuboring.\n"
        "Bekor qilish uchun /cancel."
    )
    return BROADCAST_MSG

async def broadcast_message(update: Update, context: CallbackContext):
    users_list = get_all_users()
    sent = failed = 0
    await update.message.reply_text(f"⏳ Xabar {len(users_list)} ta foydalanuvchiga yuborilmoqda...")
    for uid in users_list:
        try:
            await update.message.copy(chat_id=uid)
            sent += 1
        except Exception as e:
            logger.warning(f"Yuborilmadi {uid}: {e}")
            failed += 1
        await asyncio.sleep(0.05)
    await update.message.reply_text(f"✅ Yuborildi: {sent}\n❌ Xatolik: {failed}")
    return ConversationHandler.END

async def broadcast_cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("🚫 Broadcast bekor qilindi.")
    return ConversationHandler.END

async def unknown(update: Update, context: CallbackContext):
    await update.message.reply_text("❓ Tushunarsiz buyruq.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("users", users_command))  # o'zgartirildi
    app.add_handler(CommandHandler("toggle_apk", toggle_apk))

    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_message)]},
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    app.add_handler(broadcast_conv)
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    app.run_polling()

if __name__ == "__main__":
    main()
