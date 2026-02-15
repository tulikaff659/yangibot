import os
import logging
import asyncio
from typing import Set, Dict, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackContext,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
BROADCAST_MSG = 1
BROADCAST_BUTTON = 2
BROADCAST_BUTTON_TEXT = 3
BROADCAST_BUTTON_URL = 4

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
APK_LINK = os.getenv("APK_LINK", "https://example.com/app.apk")
# Sticker file_id (o'zingizning stikeringizni qo'ying, masalan start uchun)
START_STICKER = os.getenv("START_STICKER", "CAACAgIAAxkBAAEBuO9kvtG8lz8p2f8Q2s8X8s8X8s8X8s8X")  # O'rniga o'zingizning stiker ID ni qo'ying

missing_vars = []
if not BOT_TOKEN:
    missing_vars.append("BOT_TOKEN")
if not ADMIN_ID:
    missing_vars.append("ADMIN_ID")
try:
    ADMIN_ID = int(ADMIN_ID) if ADMIN_ID else None
except ValueError:
    missing_vars.append("ADMIN_ID (integer bo'lishi kerak)")

if missing_vars:
    raise ValueError(f"Kerakli o'zgaruvchilar topilmadi: {', '.join(missing_vars)}")

# In-memory storage
users_set: Set[int] = set()
settings_dict: Dict[str, str] = {"apk_enabled": "false"}

def add_user(user_id: int):
    users_set.add(user_id)

def get_user_count() -> int:
    return len(users_set)

def get_all_users() -> list[int]:
    return list(users_set)

def get_setting(key: str) -> str:
    return settings_dict.get(key, "false")

def set_setting(key: str, value: str):
    settings_dict[key] = value

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID

# /start command
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    add_user(user.id)

    # Sticker yuborish (agar mavjud bo'lsa)
    try:
        await update.message.reply_sticker(START_STICKER)
    except Exception as e:
        logger.warning(f"Sticker yuborilmadi: {e}")

    text = (
        "🌟 *Betwinner rasmiy boti* 🌟\n\n"
        "Endi Telegramdan chiqmagan holda *betslarni amalga oshirishingiz mumkin*.\n"
        "Ekran pastki qismidagi *BetsPlay* tugmasini bosib, Betwinner sahifasiga oʻting va "
        "betslarni amalga oshiring.\n\n"
        "Foydalanuvchilarga qulaylik tilagan holda, *Betwinner*! 🎉\n\n"
        "Quyidagi tugma orqali APK yuklab oling:"
    )

    keyboard = []
    if get_setting("apk_enabled") == "true":
        keyboard.append([InlineKeyboardButton("📥 APK yuklash", url=APK_LINK)])
        text += "\n\n👇 *APK yuklash tugmasi* 👇"
    else:
        text += "\n\nAPK yuklash hozircha mavjud emas."

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

# /users command (admin only)
async def users(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    count = get_user_count()
    await update.message.reply_text(f"👥 Foydalanuvchilar soni: {count}")

# /toggle_apk command (admin only)
async def toggle_apk(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    current = get_setting("apk_enabled")
    new = "false" if current == "true" else "true"
    set_setting("apk_enabled", new)
    status = "yoqildi ✅" if new == "true" else "o'chirildi ❌"
    await update.message.reply_text(f"APK tugmasi {status}.")

# Broadcast conversation
async def broadcast_start(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📨 *Broadcast xabarini yuborish*\n\n"
        "Endi barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring.\n"
        "Bu matn, rasm, video, hujjat bo'lishi mumkin.\n\n"
        "Keyingi qadamda xabarga tugma qo'shishingiz mumkin.\n"
        "Bekor qilish uchun /cancel yuboring.",
        parse_mode="Markdown"
    )
    return BROADCAST_MSG

async def broadcast_message_received(update: Update, context: CallbackContext):
    # Xabarni vaqtincha context.user_data ga saqlaymiz
    context.user_data['broadcast_message'] = update.message
    await update.message.reply_text(
        "Xabar qabul qilindi.\n\n"
        "Ushbu xabarga tugma qo'shishni xohlaysizmi? (ha/yo'q)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Ha ✅", callback_data="broadcast_btn_yes"),
             InlineKeyboardButton("Yo'q ❌", callback_data="broadcast_btn_no")]
        ])
    )
    return BROADCAST_BUTTON

async def broadcast_button_choice(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.data == "broadcast_btn_yes":
        await query.edit_message_text(
            "Tugma matnini kiriting (masalan: 'Betwinner sayti'):"
        )
        return BROADCAST_BUTTON_TEXT
    else:
        # Tugma yo'q, to'g'ridan-to'g'ri yuborish
        await send_broadcast(update, context, None)
        return ConversationHandler.END

async def broadcast_button_text(update: Update, context: CallbackContext):
    context.user_data['button_text'] = update.message.text
    await update.message.reply_text(
        "Endi tugma URL manzilini kiriting (masalan: https://betwinner.com):"
    )
    return BROADCAST_BUTTON_URL

async def broadcast_button_url(update: Update, context: CallbackContext):
    button_url = update.message.text.strip()
    context.user_data['button_url'] = button_url
    await send_broadcast(update, context, (context.user_data['button_text'], button_url))
    return ConversationHandler.END

async def send_broadcast(update: Update, context: CallbackContext, button: Optional[Tuple[str, str]]):
    # Foydalanuvchilar ro'yxatini olish
    users_list = get_all_users()
    sent = 0
    failed = 0

    # Xabar va tugmani tayyorlash
    original_message = context.user_data.get('broadcast_message')
    if not original_message:
        await update.message.reply_text("Xatolik: xabar topilmadi.")
        return

    reply_markup = None
    if button:
        keyboard = [[InlineKeyboardButton(button[0], url=button[1])]]
        reply_markup = InlineKeyboardMarkup(keyboard)

    # Xabar yuborish
    await update.message.reply_text(f"⏳ Xabar {len(users_list)} ta foydalanuvchiga yuborilmoqda...")

    for uid in users_list:
        try:
            # original_message ni nusxalash
            if original_message.text:
                await context.bot.send_message(
                    chat_id=uid,
                    text=original_message.text,
                    parse_mode=original_message.parse_mode,
                    entities=original_message.entities,
                    reply_markup=reply_markup
                )
            elif original_message.photo:
                await context.bot.send_photo(
                    chat_id=uid,
                    photo=original_message.photo[-1].file_id,
                    caption=original_message.caption,
                    caption_entities=original_message.caption_entities,
                    reply_markup=reply_markup
                )
            elif original_message.video:
                await context.bot.send_video(
                    chat_id=uid,
                    video=original_message.video.file_id,
                    caption=original_message.caption,
                    caption_entities=original_message.caption_entities,
                    reply_markup=reply_markup
                )
            elif original_message.document:
                await context.bot.send_document(
                    chat_id=uid,
                    document=original_message.document.file_id,
                    caption=original_message.caption,
                    caption_entities=original_message.caption_entities,
                    reply_markup=reply_markup
                )
            # Boshqa turlar uchun ham qo'shish mumkin
            else:
                # oddiy matn sifatida yuborish
                await context.bot.send_message(
                    chat_id=uid,
                    text=original_message.text or "Xabar",
                    reply_markup=reply_markup
                )
            sent += 1
        except Exception as e:
            logger.warning(f"Yuborilmadi {uid}: {e}")
            failed += 1
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"✅ Xabar yuborildi:\n"
        f"• Muvaffaqiyatli: {sent}\n"
        f"• Xatolik: {failed}"
    )

async def broadcast_cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("🚫 Broadcast bekor qilindi.")
    return ConversationHandler.END

async def unknown(update: Update, context: CallbackContext):
    await update.message.reply_text("❓ Tushunarsiz buyruq.")

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("users", users))
    application.add_handler(CommandHandler("toggle_apk", toggle_apk))

    # Broadcast conversation handler
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_message_received)],
            BROADCAST_BUTTON: [MessageHandler(filters.Regex('^(ha|yoq)$'), broadcast_button_choice)],
            BROADCAST_BUTTON_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_button_text)],
            BROADCAST_BUTTON_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_button_url)],
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
        per_message=False,
    )
    application.add_handler(broadcast_conv)

    # Callback query handler for button choice
    application.add_handler(CallbackQueryHandler(broadcast_button_choice, pattern="^broadcast_btn_"))

    # Unknown commands
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    application.run_polling()

if __name__ == "__main__":
    main()
