import json
import logging
import os
import asyncio
import random
from pathlib import Path
from typing import Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ------------------- SOZLAMALAR -------------------
TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = 6935090105  # Admin Telegram ID

# Fayl yo'llari
DATA_FILE = "games.json"
USERS_FILE = "users.json"
APK_FILE = "apk.json"

REFERRAL_BONUS = 2500  # Har bir taklif uchun bonus
START_BONUS = 15000     # Start bonusi
MIN_WITHDRAW = 25000    # Minimal yechish summasi
BOT_USERNAME = "BETWINNERplay_bot"  # ✅ TO'G'RI USERNAME
WITHDRAW_SITE_URL = "https://futbolinsidepulyechish.netlify.app/"

# ------------------- LOGLASH -------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------- MAʼLUMOTLAR SAQLASH -------------------
def load_games() -> Dict:
    if Path(DATA_FILE).exists():
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_games(games: Dict):
    with open(DATA_FILE, "w") as f:
        json.dump(games, f)

def load_users() -> Dict:
    if Path(USERS_FILE).exists():
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users: Dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

def load_apk() -> Dict:
    if Path(APK_FILE).exists():
        with open(APK_FILE, "r") as f:
            return json.load(f)
    return {"file_id": None}

def save_apk(apk_data: Dict):
    with open(APK_FILE, "w") as f:
        json.dump(apk_data, f)

games_data = load_games()
users_data = load_users()
apk_data = load_apk()

# ------------------- YORDAMCHI FUNKSIYALAR -------------------
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def generate_unique_code() -> str:
    """Har bir foydalanuvchi uchun unikal kod yaratish"""
    while True:
        code = f"{random.randint(0, 9999999):07d}"
        existing_codes = []
        for user_data in users_data.values():
            if user_data.get("referral_code"):
                existing_codes.append(user_data["referral_code"])
        if code not in existing_codes:
            return code

def get_referral_link(user_id: int) -> str:
    """Foydalanuvchi uchun referral havola"""
    user_id_str = str(user_id)
    if user_id_str in users_data and users_data[user_id_str].get("referral_code"):
        code = users_data[user_id_str]["referral_code"]
    else:
        code = generate_unique_code()
        if user_id_str in users_data:
            users_data[user_id_str]["referral_code"] = code
            save_users(users_data)
    
    return f"https://t.me/{BOT_USERNAME}?start=ref_{code}"

def get_main_keyboard() -> InlineKeyboardMarkup:
    """Asosiy menyu tugmalari"""
    keyboard = [
        [
            InlineKeyboardButton("📊 Kun stavkasi", callback_data="show_games"),
            InlineKeyboardButton("📱 BetWinner APK", callback_data="show_apk")
        ],
        [
            InlineKeyboardButton("💰 Pul ishlash", callback_data="earn"),
            InlineKeyboardButton("💵 Balans", callback_data="balance")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Bosh menyuga qaytish tugmasi"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")]])

def get_games_keyboard() -> InlineKeyboardMarkup:
    """Kun stavkalari ro'yxati"""
    keyboard = []
    for game in games_data.keys():
        keyboard.append([InlineKeyboardButton(game, callback_data=f"game_{game}")])
    keyboard.append([InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

async def ensure_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    """Yangi foydalanuvchi yaratish yoki mavjudini olish"""
    user_id_str = str(user_id)
    
    if user_id_str not in users_data:
        # Yangi foydalanuvchi
        new_code = generate_unique_code()
        users_data[user_id_str] = {
            "balance": 0,
            "referred_by": None,
            "referrals": 0,
            "referral_code": new_code,
            "start_bonus_given": False,
            "withdraw_code": generate_unique_code(),
            "username": username,
            "first_name": first_name,
            "joined_at": str(asyncio.get_event_loop().time())
        }
        save_users(users_data)
        logger.info(f"✅ Yangi foydalanuvchi: {user_id} (kodi: {new_code})")
    else:
        # Agar referral kodi bo'lmasa, qo'shish
        if "referral_code" not in users_data[user_id_str]:
            users_data[user_id_str]["referral_code"] = generate_unique_code()
            save_users(users_data)
    
    return users_data[user_id_str]

async def give_start_bonus(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """1.5 daqiqadan keyin start bonusini berish"""
    await asyncio.sleep(90)
    user_id_str = str(user_id)
    
    if user_id_str in users_data and not users_data[user_id_str].get("start_bonus_given", False):
        users_data[user_id_str]["balance"] += START_BONUS
        users_data[user_id_str]["start_bonus_given"] = True
        save_users(users_data)
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 Tabriklaymiz! Sizga start bonusi sifatida {START_BONUS} so‘m berildi!"
            )
        except:
            pass

# ------------------- START HANDLER -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start komandasi - eski holatidagidek"""
    user = update.effective_user
    user_id = user.id
    args = context.args

    # Foydalanuvchini yaratish
    user_data = await ensure_user(user_id, user.username, user.first_name)

    # Referralni tekshirish (format: ref_ABC1234)
    if args and args[0].startswith("ref_"):
        referral_code = args[0].replace("ref_", "")
        
        logger.info(f"Referral kod: {referral_code} (user: {user_id})")
        
        # Referral kod orqali taklif qiluvchini topish
        referrer_id = None
        for uid, data in users_data.items():
            if data.get("referral_code") == referral_code and uid != str(user_id):
                referrer_id = uid
                break
        
        # Agar taklif qiluvchi topilsa va bu foydalanuvchi hali taklif qilinmagan bo'lsa
        if referrer_id and not user_data.get("referred_by"):
            logger.info(f"Referral topildi: {referrer_id} -> {user_id}")
            
            # Referralni belgilash
            user_data["referred_by"] = referrer_id
            save_users(users_data)
            
            # Taklif qiluvchiga bonus berish
            users_data[referrer_id]["balance"] += REFERRAL_BONUS
            users_data[referrer_id]["referrals"] += 1
            save_users(users_data)
            
            # Taklif qiluvchiga xabar
            try:
                referrer_name = user.first_name or user.username or "Foydalanuvchi"
                
                await context.bot.send_message(
                    chat_id=int(referrer_id),
                    text=(
                        f"🎉 *Yangi do‘st qo‘shildi!*\n\n"
                        f"👤 {referrer_name}\n"
                        f"💰 Balansingizga {REFERRAL_BONUS} so‘m qo‘shildi.\n"
                        f"💵 Hozirgi balans: {users_data[referrer_id]['balance']} so‘m\n"
                        f"👥 Jami do‘stlaringiz: {users_data[referrer_id]['referrals']}"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Referrer xabar yuborishda xatolik: {e}")

    # Start bonusini rejalashtirish
    if not user_data.get("start_bonus_given", False):
        asyncio.create_task(give_start_bonus(user_id, context))

    # Eski start xabari
    text = (
        "🎰 *BetWinner Bukmekeriga xush kelibsiz!* 🎰\n\n"
        "🔥 *Premium bonuslar* va har hafta yangi yutuqlar sizni kutmoqda!\n"
        "📊 *O‘yinlar uchun chuqur taxlili.\n\n"
        "📢 *BetWinner kun kuponlari* va eng so‘nggi aksiyalar haqida tezkor xabarlar!\n"
        "✅ Kunlik stavkalar, ekspress kuponlar va bonus imkoniyatlaridan birinchi bo‘lib xabardor bo‘ling.\n\n"
        "💰 Bu yerda nafaqat o‘ynab, balki *pul ishlashingiz* mumkin:\n"
        "– Do‘stlaringizni taklif qiling va har bir taklif uchun *2500 so‘m* oling.\n"
        "– Start bonus sifatida *15000 so‘m* hamyoningizga tushadi.\n\n"
        "👇 Quyidagi tugmalar orqali imkoniyatlarni kashf eting:"
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# ------------------- QOLGAN HANDLERLAR (o'zgarmaydi) -------------------
# ... (show_games, game_callback, show_apk, earn_callback, balance_callback, 
#      withdraw_callback, admin buyruqlari va h.k.)

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bosh menyuga qaytish"""
    query = update.callback_query
    await query.answer()
    text = (
        "🎰 *BetWinner Bukmekeriga xush kelibsiz!* 🎰\n\n"
        "👇 Quyidagi tugmalar orqali imkoniyatlarni kashf eting:"
    )
    await query.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# ------------------- MAIN -------------------
def main():
    app = Application.builder().token(TOKEN).build()

    # Asosiy handlerlar
    app.add_handler(CommandHandler("start", start))
    
    # Admin buyruqlari
    app.add_handler(CommandHandler("newapk", newapk))
    app.add_handler(CommandHandler("deleteapk", deleteapk))
    app.add_handler(CommandHandler("newkupon", newkupon))
    app.add_handler(CommandHandler("deletekupon", deletekupon))
    app.add_handler(CommandHandler("new", new))
    app.add_handler(CommandHandler("skip", skip))
    
    # Callback handlerlar
    app.add_handler(CallbackQueryHandler(show_games, pattern="^show_games$"))
    app.add_handler(CallbackQueryHandler(show_apk, pattern="^show_apk$"))
    app.add_handler(CallbackQueryHandler(game_callback, pattern="^game_"))
    app.add_handler(CallbackQueryHandler(earn_callback, pattern="^earn$"))
    app.add_handler(CallbackQueryHandler(balance_callback, pattern="^balance$"))
    app.add_handler(CallbackQueryHandler(withdraw_callback, pattern="^withdraw$"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^main_menu$"))
    
    # Xabarlarni qabul qilish
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    logger.info("✅ Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
