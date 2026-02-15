import os
import logging
from datetime import datetime
from typing import Optional

import asyncpg
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackContext,
)

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for broadcast conversation
BROADCAST_MSG = 1

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
APK_LINK = os.getenv("APK_LINK", "https://example.com/app.apk")  # default link
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN or not ADMIN_ID or not DATABASE_URL:
    raise ValueError("BOT_TOKEN, ADMIN_ID va DATABASE_URL muhit o'zgaruvchilari majburiy.")

# Database connection pool
pool: Optional[asyncpg.Pool] = None


async def init_db():
    """Create tables if they don't exist."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    async with pool.acquire() as conn:
        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                registered_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Settings table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # Insert default setting if not exists
        await conn.execute("""
            INSERT INTO settings (key, value)
            VALUES ('apk_enabled', 'false')
            ON CONFLICT (key) DO NOTHING
        """)


async def add_user(user_id: int, username: str, first_name: str, last_name: str):
    """Add a new user to the database."""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, registered_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, username, first_name, last_name, datetime.now())


async def get_user_count() -> int:
    """Return total number of users."""
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")


async def get_all_users() -> list[int]:
    """Return list of all user IDs."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
        return [row["user_id"] for row in rows]


async def get_setting(key: str) -> str:
    """Get a setting value."""
    async with pool.acquire() as conn:
        value = await conn.fetchval("SELECT value FROM settings WHERE key = $1", key)
        return value or "false"


async def set_setting(key: str, value: str):
    """Set a setting value."""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO settings (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, key, value)


def is_admin(update: Update) -> bool:
    """Check if the user is admin."""
    return update.effective_user.id == ADMIN_ID


# /start command
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    await add_user(user.id, user.username, user.first_name, user.last_name)

    # Welcome message
    text = (
        "🌟 *Betwinner rasmiy boti* 🌟\n\n"
        "Endi Telegramdan chiqmagan holda *betslarni amalga oshirishingiz mumkin*.\n"
        "Ekran pastki qismidagi *BetsPlay* tugmasini bosib Betwinner sahifasiga oʻting va "
        "betslarni amalga oshiring.\n\n"
        "Foydalanuvchilarga qulaylik tilagan holda, *Betwinner*! 🎉"
    )

    # Inline keyboard
    keyboard = []
    apk_enabled = await get_setting("apk_enabled")
    if apk_enabled == "true":
        keyboard.append([InlineKeyboardButton("📥 APK yuklash", url=APK_LINK)])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


# /users command (admin only)
async def users(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    count = await get_user_count()
    await update.message.reply_text(f"👥 Foydalanuvchilar soni: {count}")


# /toggle_apk command (admin only)
async def toggle_apk(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return

    current = await get_setting("apk_enabled")
    new_value = "false" if current == "true" else "true"
    await set_setting("apk_enabled", new_value)
    status = "yoqildi ✅" if new_value == "true" else "oʻchirildi ❌"
    await update.message.reply_text(f"APK tugmasi {status}.")


# Broadcast conversation entry point
async def broadcast_start(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📨 Endi barcha foydalanuvchilarga yubormoqchi boʻlgan xabaringizni yuboring.\n"
        "(Matn, rasm, video, hujjat – istalgan formatda boʻlishi mumkin)\n"
        "Bekor qilish uchun /cancel yuboring."
    )
    return BROADCAST_MSG


async def broadcast_message(update: Update, context: CallbackContext):
    """Receive the message to broadcast and send it to all users."""
    users = await get_all_users()
    sent = 0
    failed = 0

    await update.message.reply_text(f"⏳ Xabar {len(users)} ta foydalanuvchiga yuborilmoqda...")

    for uid in users:
        try:
            # Copy the message (preserves media, formatting, etc.)
            await update.message.copy(chat_id=uid)
            sent += 1
        except Exception as e:
            logger.warning(f"Yuborilmadi {uid}: {e}")
            failed += 1
        # Avoid flood limits
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"✅ Xabar yuborildi:\n"
        f"• Muvaffaqiyatli: {sent}\n"
        f"• Xatolik: {failed}"
    )
    return ConversationHandler.END


async def broadcast_cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("🚫 Broadcast bekor qilindi.")
    return ConversationHandler.END


# Fallback for unknown commands
async def unknown(update: Update, context: CallbackContext):
    await update.message.reply_text("❓ Tushunarsiz buyruq.")


def main():
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("users", users))
    application.add_handler(CommandHandler("toggle_apk", toggle_apk))

    # Broadcast conversation handler
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_message)],
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    application.add_handler(broadcast_conv)

    # Unknown commands
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    # Start bot
    application.run_polling()


if __name__ == "__main__":
    import asyncio

    # Initialize database before running
    asyncio.run(init_db())
    main()
