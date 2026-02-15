import os
import logging
import asyncio
from datetime import datetime
from typing import Optional

import asyncpg
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

# States for broadcast conversation
BROADCAST_MSG = 1

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
APK_LINK = os.getenv("APK_LINK", "https://example.com/app.apk")

# Check required variables
missing_vars = []
if not BOT_TOKEN:
    missing_vars.append("BOT_TOKEN")
if not ADMIN_ID:
    missing_vars.append("ADMIN_ID")
try:
    ADMIN_ID = int(ADMIN_ID) if ADMIN_ID else None
except ValueError:
    logger.error("ADMIN_ID must be an integer")
    missing_vars.append("ADMIN_ID (invalid format)")

if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Try to build from individual variables (Railway provides these)
    pg_host = os.getenv("PGHOST")
    pg_port = os.getenv("PGPORT", "5432")
    pg_user = os.getenv("PGUSER")
    pg_password = os.getenv("PGPASSWORD")
    pg_database = os.getenv("PGDATABASE")
    if all([pg_host, pg_user, pg_password, pg_database]):
        DATABASE_URL = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
        logger.info("DATABASE_URL built from individual PG variables")
    else:
        raise ValueError("Neither DATABASE_URL nor individual PG variables found. Add PostgreSQL plugin.")

pool: Optional[asyncpg.Pool] = None


async def init_db():
    """Create tables if they don't exist."""
    global pool
    try:
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
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


async def add_user(user_id: int, username: str, first_name: str, last_name: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, registered_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, username, first_name, last_name, datetime.now())


async def get_user_count() -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")


async def get_all_users() -> list[int]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
        return [row["user_id"] for row in rows]


async def get_setting(key: str) -> str:
    async with pool.acquire() as conn:
        value = await conn.fetchval("SELECT value FROM settings WHERE key = $1", key)
        return value or "false"


async def set_setting(key: str, value: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO settings (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, key, value)


def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


# /start command
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    await add_user(user.id, user.username, user.first_name, user.last_name)

    text = (
        "🌟 *Betwinner rasmiy boti* 🌟\n\n"
        "Endi Telegramdan chiqmagan holda *betslarni amalga oshirishingiz mumkin*.\n"
        "Ekran pastki qismidagi *BetsPlay* tugmasini bosib Betwinner sahifasiga oʻting va "
        "betslarni amalga oshiring.\n\n"
        "Foydalanuvchilarga qulaylik tilagan holda, *Betwinner*! 🎉"
    )

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


# Broadcast conversation
async def broadcast_start(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📨 Endi barcha foydalanuvchilarga yubormoqchi boʻlgan xabaringizni yuboring.\n"
        "(Matn, rasm, video, hujjat – istalgan formatda)\n"
        "Bekor qilish uchun /cancel yuboring."
    )
    return BROADCAST_MSG


async def broadcast_message(update: Update, context: CallbackContext):
    users = await get_all_users()
    sent = 0
    failed = 0

    await update.message.reply_text(f"⏳ Xabar {len(users)} ta foydalanuvchiga yuborilmoqda...")

    for uid in users:
        try:
            await update.message.copy(chat_id=uid)
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
    return ConversationHandler.END


async def broadcast_cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("🚫 Broadcast bekor qilindi.")
    return ConversationHandler.END


async def unknown(update: Update, context: CallbackContext):
    await update.message.reply_text("❓ Tushunarsiz buyruq.")


async def post_init(application: Application):
    await init_db()


def main():
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("users", users))
    application.add_handler(CommandHandler("toggle_apk", toggle_apk))

    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_message)],
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    application.add_handler(broadcast_conv)
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    application.run_polling()


if __name__ == "__main__":
    main()
