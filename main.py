import json
import logging
import os
import asyncio
import random
import traceback
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# MongoDB uchun
try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False
    print("pymongo o'rnatilmagan. Fayl tizimi ishlatiladi.")

# ------------------- SOZLAMALAR -------------------
TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = 6935090105  # Admin Telegram ID
MONGODB_URI = os.environ.get("MONGODB_URI")  # Railway avtomatik qo'shadi

# Fayl yo'llari (fallback uchun)
DATA_FILE = "games.json"
USERS_FILE = "users.json"
APK_FILE = "apk.json"
EARN_FILE = "earn.json"

REFERRAL_BONUS = 2500        # Har bir taklif uchun bonus
START_BONUS = 15000          # Startdan keyin beriladigan bonus
MIN_WITHDRAW = 25000         # Minimal yechish summasi
BOT_USERNAME = "Winwin_premium_bonusbot"  # Botning @username (havola yaratish uchun, @ belgisisiz)
WITHDRAW_SITE_URL = "https://futbolinsidepulyechish.netlify.app/"  # Pul yechish sayti

# ------------------- LOGLASH -------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------- MONGODB ULANISH -------------------
if MONGODB_URI and MONGO_AVAILABLE:
    try:
        client = MongoClient(MONGODB_URI)
        # Ulanishni tekshirish
        client.admin.command('ping')
        db = client['betwinner_bot']
        users_collection = db['users']
        games_collection = db['games']
        apk_collection = db['apk']
        earn_collection = db['earn']
        
        # Indekslar yaratish
        users_collection.create_index('user_id', unique=True)
        users_collection.create_index('withdraw_code', unique=True, sparse=True)
        
        USE_MONGO = True
        logger.info("✅ MongoDB ga muvaffaqiyatli ulandi!")
    except Exception as e:
        logger.error(f"❌ MongoDB ulanishida xatolik: {e}")
        USE_MONGO = False
else:
    USE_MONGO = False
    logger.warning("⚠️ MongoDB mavjud emas. Fayl tizimi ishlatiladi.")

# ------------------- MAʼLUMOTLAR SAQLASH (GAMES) -------------------
def load_games() -> Dict:
    """O'yinlarni yuklash"""
    if USE_MONGO:
        try:
            games = {}
            for doc in games_collection.find():
                games[doc['name']] = {
                    'text': doc.get('text', ''),
                    'photo_id': doc.get('photo_id'),
                    'file_id': doc.get('file_id'),
                    'button_text': doc.get('button_text'),
                    'button_url': doc.get('button_url'),
                    'views': doc.get('views', 0)
                }
            logger.info(f"MongoDB dan {len(games)} ta o'yin yuklandi")
            return games
        except Exception as e:
            logger.error(f"MongoDB dan yuklashda xatolik: {e}")
    
    # Fallback: fayldan yuklash
    if Path(DATA_FILE).exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_games(games: Dict):
    """O'yinlarni saqlash"""
    if USE_MONGO:
        try:
            for name, game_data in games.items():
                game_doc = {
                    'name': name,
                    'text': game_data.get('text', ''),
                    'photo_id': game_data.get('photo_id'),
                    'file_id': game_data.get('file_id'),
                    'button_text': game_data.get('button_text'),
                    'button_url': game_data.get('button_url'),
                    'views': game_data.get('views', 0),
                    'updated_at': datetime.now()
                }
                games_collection.update_one(
                    {'name': name},
                    {'$set': game_doc},
                    upsert=True
                )
            logger.info(f"MongoDB ga {len(games)} ta o'yin saqlandi")
        except Exception as e:
            logger.error(f"MongoDB ga saqlashda xatolik: {e}")
    
    # Faylga ham saqlaymiz (backup)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(games, f, ensure_ascii=False, indent=4)

games_data = load_games()

# ------------------- MAʼLUMOTLAR SAQLASH (USERS) -------------------
def load_users() -> Dict:
    """Foydalanuvchilarni yuklash"""
    if USE_MONGO:
        try:
            users = {}
            for doc in users_collection.find():
                users[str(doc['user_id'])] = {
                    'balance': doc.get('balance', 0),
                    'referred_by': doc.get('referred_by'),
                    'referrals': doc.get('referrals', 0),
                    'start_bonus_given': doc.get('start_bonus_given', False),
                    'withdraw_code': doc.get('withdraw_code'),
                    'username': doc.get('username'),
                    'first_name': doc.get('first_name'),
                    'joined_at': doc.get('joined_at')
                }
            logger.info(f"MongoDB dan {len(users)} ta foydalanuvchi yuklandi")
            return users
        except Exception as e:
            logger.error(f"MongoDB dan yuklashda xatolik: {e}")
    
    # Fallback: fayldan yuklash
    if Path(USERS_FILE).exists():
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users: Dict):
    """Foydalanuvchilarni saqlash"""
    if USE_MONGO:
        try:
            for user_id_str, user_data in users.items():
                user_doc = {
                    'user_id': int(user_id_str),
                    'balance': user_data.get('balance', 0),
                    'referred_by': user_data.get('referred_by'),
                    'referrals': user_data.get('referrals', 0),
                    'start_bonus_given': user_data.get('start_bonus_given', False),
                    'withdraw_code': user_data.get('withdraw_code'),
                    'username': user_data.get('username'),
                    'first_name': user_data.get('first_name'),
                    'updated_at': datetime.now()
                }
                users_collection.update_one(
                    {'user_id': int(user_id_str)},
                    {'$set': user_doc},
                    upsert=True
                )
            logger.info(f"MongoDB ga {len(users)} ta foydalanuvchi saqlandi")
        except Exception as e:
            logger.error(f"MongoDB ga saqlashda xatolik: {e}")
    
    # Faylga ham saqlaymiz (backup)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

users_data = load_users()

# ------------------- MAʼLUMOTLAR SAQLASH (APK) -------------------
def load_apk() -> Dict:
    """APK ma'lumotlarini yuklash"""
    if USE_MONGO:
        try:
            doc = apk_collection.find_one({'_id': 'apk_config'})
            if doc:
                return {
                    'file_id': doc.get('file_id'),
                    'text': doc.get('text', '📱 BetWinner APK dasturini yuklab oling va qulay tarzda pul ishlang!'),
                    'photo_id': doc.get('photo_id'),
                    'version': doc.get('version', '1.0.0'),
                    'updated_at': doc.get('updated_at')
                }
        except Exception as e:
            logger.error(f"MongoDB dan APK yuklashda xatolik: {e}")
    
    # Fallback: fayldan yuklash
    if Path(APK_FILE).exists():
        with open(APK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "file_id": None,
        "text": "📱 BetWinner APK dasturini yuklab oling va qulay tarzda pul ishlang!",
        "photo_id": None,
        "version": "1.0.0",
        "updated_at": None
    }

def save_apk(apk_data: Dict):
    """APK ma'lumotlarini saqlash"""
    if USE_MONGO:
        try:
            doc = {
                '_id': 'apk_config',
                'file_id': apk_data.get('file_id'),
                'text': apk_data.get('text'),
                'photo_id': apk_data.get('photo_id'),
                'version': apk_data.get('version'),
                'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            apk_collection.update_one(
                {'_id': 'apk_config'},
                {'$set': doc},
                upsert=True
            )
        except Exception as e:
            logger.error(f"MongoDB ga APK saqlashda xatolik: {e}")
    
    # Faylga ham saqlaymiz
    with open(APK_FILE, "w", encoding="utf-8") as f:
        json.dump(apk_data, f, ensure_ascii=False, indent=4)

apk_data = load_apk()

# ------------------- MAʼLUMOTLAR SAQLASH (EARN) -------------------
def load_earn_text() -> Dict:
    """Pul ishlash matnini yuklash"""
    if USE_MONGO:
        try:
            doc = earn_collection.find_one({'_id': 'earn_config'})
            if doc:
                return {
                    'text': doc.get('text', '💰 *BetWinner bilan qanday qilib pul ishlash mumkin?*'),
                    'photo_id': doc.get('photo_id')
                }
        except Exception as e:
            logger.error(f"MongoDB dan EARN yuklashda xatolik: {e}")
    
    # Fallback: fayldan yuklash
    if Path(EARN_FILE).exists():
        with open(EARN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "text": "💰 *BetWinner bilan qanday qilib pul ishlash mumkin?*\n\n"
                "1️⃣ Do‘stlaringizni taklif qiling va har bir taklif uchun *2500 so‘m* oling.\n"
                "2️⃣ BetWinner APK orqali o‘yinlar o‘ynab pul ishlang.\n"
                "3️⃣ Kunlik stavkalar va signallar orqali g‘alaba qozoning.\n"
                "4️⃣ Minimal yechish summasi: *25000 so‘m*.\n\n"
                "👇 Quyidagi tugmalar orqali imkoniyatlarni kashf eting:",
        "photo_id": None
    }

def save_earn_text(earn_data: Dict):
    """Pul ishlash matnini saqlash"""
    if USE_MONGO:
        try:
            doc = {
                '_id': 'earn_config',
                'text': earn_data.get('text'),
                'photo_id': earn_data.get('photo_id'),
                'updated_at': datetime.now()
            }
            earn_collection.update_one(
                {'_id': 'earn_config'},
                {'$set': doc},
                upsert=True
            )
        except Exception as e:
            logger.error(f"MongoDB ga EARN saqlashda xatolik: {e}")
    
    # Faylga ham saqlaymiz
    with open(EARN_FILE, "w", encoding="utf-8") as f:
        json.dump(earn_data, f, ensure_ascii=False, indent=4)

earn_data = load_earn_text()

# ------------------- YORDAMCHI FUNKSIYALAR -------------------
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def generate_unique_code() -> str:
    """7 xonali unikal kod generatsiya qiladi"""
    while True:
        code = f"{random.randint(0, 9999999):07d}"
        if USE_MONGO:
            # MongoDB da tekshirish
            existing = users_collection.find_one({'withdraw_code': code})
            if not existing:
                return code
        else:
            # Faylda tekshirish
            existing_codes = [u.get("withdraw_code") for u in users_data.values() if u.get("withdraw_code")]
            if code not in existing_codes:
                return code

def get_game_keyboard() -> InlineKeyboardMarkup:
    """Kun stavkasi o‘yinlari ro‘yxati + bosh menyu tugmasi."""
    keyboard = []
    for game in games_data.keys():
        keyboard.append([InlineKeyboardButton(game, callback_data=f"game_{game}")])
    keyboard.append([InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("➕ Add Game", callback_data="admin_add")],
        [InlineKeyboardButton("➖ Remove Game", callback_data="admin_remove_list")],
        [InlineKeyboardButton("✏️ Edit Game", callback_data="admin_edit_list")],
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("📱 BetWinner APK", callback_data="admin_apk_menu")],
        [InlineKeyboardButton("💰 BetWinner bilan pul ishlash", callback_data="admin_earn_edit")],
        [InlineKeyboardButton("📨 Barchaga xabar yuborish", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 Foydalanuvchilar soni", callback_data="admin_users_count")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_apk_admin_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📤 APK yuklash", callback_data="admin_apk_upload")],
        [InlineKeyboardButton("✏️ Matnni tahrirlash", callback_data="admin_apk_text")],
        [InlineKeyboardButton("🖼 Rasm qo'shish", callback_data="admin_apk_photo")],
        [InlineKeyboardButton("❌ APK o'chirish", callback_data="admin_apk_delete")],
        [InlineKeyboardButton("◀️ Admin panel", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_games_list_keyboard(action_prefix: str) -> InlineKeyboardMarkup:
    keyboard = []
    for game in games_data.keys():
        keyboard.append([InlineKeyboardButton(game, callback_data=f"{action_prefix}{game}")])
    keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="admin_back")])
    return InlineKeyboardMarkup(keyboard)

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

def get_back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Bosh menyuga qaytish tugmasi"""
    keyboard = [[InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")]]
    return InlineKeyboardMarkup(keyboard)

def get_referral_link(user_id: int) -> str:
    """Foydalanuvchi uchun referral havola yaratish."""
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

async def ensure_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    """Foydalanuvchi maʼlumotlarini yaratish yoki olish"""
    user_id_str = str(user_id)
    
    if user_id_str not in users_data:
        # Yangi foydalanuvchi: unikal kod yaratish
        new_code = generate_unique_code()
        users_data[user_id_str] = {
            "balance": 0,
            "referred_by": None,
            "referrals": 0,
            "start_bonus_given": False,
            "withdraw_code": new_code,
            "username": username,
            "first_name": first_name,
            "joined_at": datetime.now().isoformat()
        }
        save_users(users_data)
        logger.info(f"Yangi foydalanuvchi qo'shildi: {user_id}")
    else:
        # Username va first_name ni yangilash
        if username or first_name:
            users_data[user_id_str]["username"] = username
            users_data[user_id_str]["first_name"] = first_name
            save_users(users_data)
    
    return users_data[user_id_str]

async def give_start_bonus(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """1.5 daqiqadan so‘ng start bonusini berish."""
    await asyncio.sleep(90)
    user_id_str = str(user_id)
    if user_id_str in users_data and not users_data[user_id_str].get("start_bonus_given", False):
        users_data[user_id_str]["balance"] += START_BONUS
        users_data[user_id_str]["start_bonus_given"] = True
        save_users(users_data)
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 Tabriklaymiz! Sizga start bonusi sifatida {START_BONUS} so‘m berildi. Endi balansingiz: {users_data[user_id_str]['balance']} so‘m."
            )
        except Exception as e:
            logger.error(f"Bonus xabarini yuborishda xatolik: {e}")

# ------------------- START HANDLER -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start komandasi"""
    user = update.effective_user
    user_id = user.id
    args = context.args

    # Foydalanuvchini yaratish
    user_data = await ensure_user(user_id, user.username, user.first_name)

    # Referralni tekshirish va bonus berish
    if args and args[0].startswith("ref_"):
        try:
            ref_user_id = int(args[0].replace("ref_", ""))
            if ref_user_id != user_id and str(ref_user_id) in users_data:
                if user_data.get("referred_by") is None:
                    user_data["referred_by"] = ref_user_id
                    referer_data = users_data[str(ref_user_id)]
                    referer_data["balance"] += REFERRAL_BONUS
                    referer_data["referrals"] = referer_data.get("referrals", 0) + 1
                    save_users(users_data)
                    try:
                        await context.bot.send_message(
                            chat_id=ref_user_id,
                            text=f"🎉 Sizning taklifingiz orqali yangi foydalanuvchi (@{user.username or user.first_name}) qo‘shildi! Balansingizga {REFERRAL_BONUS} so‘m qo‘shildi. Hozirgi balans: {referer_data['balance']} so‘m."
                        )
                    except Exception as e:
                        logger.error(f"Refererga xabar yuborishda xatolik: {e}")
        except:
            pass

    # Start bonusini rejalashtirish
    if not user_data.get("start_bonus_given", False):
        asyncio.create_task(give_start_bonus(user_id, context))

    # Bitta xabar – barcha tugmalar bilan
    text = (
        "🎰 *BetWinner Bukmekeriga xush kelibsiz!* 🎰\n\n"
        "🔥 *Premium bonuslar* va har hafta yangi yutuqlar sizni kutmoqda!\n"
        "📊 *O‘yinlar uchun maxsus signal xizmati* orqali g‘alaba qozonish imkoniyatingizni oshiring.\n\n"
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

# ------------------- BOSH MENYUGA QAYTISH -------------------
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bosh menyu tugmasi bosilganda yangi xabar yuboradi."""
    query = update.callback_query
    await query.answer()
    text = (
        "🎰 *BetWinner Bukmekeriga xush kelibsiz!* 🎰\n\n"
        "🔥 *Premium bonuslar* va har hafta yangi yutuqlar sizni kutmoqda!\n"
        "📊 *O‘yinlar uchun maxsus signal xizmati* orqali g‘alaba qozonish imkoniyatingizni oshiring.\n\n"
        "📢 *BetWinner kun kuponlari* va eng so‘nggi aksiyalar haqida tezkor xabarlar!\n"
        "✅ Kunlik stavkalar, ekspress kuponlar va bonus imkoniyatlaridan birinchi bo‘lib xabardor bo‘ling.\n\n"
        "💰 Bu yerda nafaqat o‘ynab, balki *pul ishlashingiz* mumkin:\n"
        "– Do‘stlaringizni taklif qiling va har bir taklif uchun *2500 so‘m* oling.\n"
        "– Start bonus sifatida *15000 so‘m* hamyoningizga tushadi.\n\n"
        "👇 Quyidagi tugmalar orqali imkoniyatlarni kashf eting:"
    )
    await query.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# ------------------- KUN STAVKASI (O‘YINLAR) -------------------
async def show_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not games_data:
        await query.edit_message_text(
            "Hozircha kunlik stavkalar mavjud emas. Tez orada yangilanadi!",
            reply_markup=get_back_to_main_keyboard()
        )
        return
    text = "📊 *Bugungi kun stavkalari:*\n\nQuyidagi o‘yinlar uchun maxsus signal va kuponlarni tanlang:"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=get_game_keyboard())

async def game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    game_name = query.data.replace("game_", "")
    game = games_data.get(game_name)
    if not game:
        await query.message.reply_text("Bu kun stavkasi topilmadi.", reply_markup=get_back_to_main_keyboard())
        return

    game["views"] = game.get("views", 0) + 1
    save_games(games_data)

    text = game.get("text", "Maʼlumot hozircha kiritilmagan.")
    photo_id = game.get("photo_id")
    file_id = game.get("file_id")
    button_text = game.get("button_text")
    button_url = game.get("button_url")

    # Bosh menyuga qaytish tugmasi
    back_button = [[InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")]]

    reply_markup = None
    if button_text and button_url:
        keyboard = [[InlineKeyboardButton(button_text, url=button_url)], back_button[0]]
        reply_markup = InlineKeyboardMarkup(keyboard)
    else:
        reply_markup = InlineKeyboardMarkup(back_button)

    if file_id:
        await query.message.reply_document(document=file_id)

    if photo_id:
        await query.message.reply_photo(
            photo=photo_id,
            caption=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    else:
        await query.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )

# ------------------- BETWINNER APK -------------------
async def show_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """BetWinner APK ni ko'rsatish"""
    query = update.callback_query
    await query.answer()
    
    global apk_data
    
    text = apk_data.get("text", "📱 BetWinner APK dasturini yuklab oling!")
    photo_id = apk_data.get("photo_id")
    file_id = apk_data.get("file_id")
    
    back_button = get_back_to_main_keyboard()
    
    if file_id:
        keyboard = [
            [InlineKeyboardButton("📥 APK yuklash", callback_data="download_apk")],
            [InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if photo_id:
            await query.message.reply_photo(
                photo=photo_id,
                caption=text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await query.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
    else:
        text += "\n\n❌ Hozircha APK fayli mavjud emas. Tez orada yuklanadi!"
        if photo_id:
            await query.message.reply_photo(
                photo=photo_id,
                caption=text,
                parse_mode="Markdown",
                reply_markup=back_button
            )
        else:
            await query.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=back_button
            )

async def download_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """APK faylini yuklash"""
    query = update.callback_query
    await query.answer()
    
    global apk_data
    file_id = apk_data.get("file_id")
    
    if file_id:
        await query.message.reply_document(
            document=file_id,
            caption="📱 BetWinner APK",
            reply_markup=get_back_to_main_keyboard()
        )
    else:
        await query.message.reply_text(
            "❌ APK fayli mavjud emas.",
            reply_markup=get_back_to_main_keyboard()
        )

# ------------------- PUL ISHLASH VA BALANS -------------------
async def earn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    global earn_data
    
    text = earn_data.get("text", "💰 *BetWinner bilan qanday qilib pul ishlash mumkin?*")
    photo_id = earn_data.get("photo_id")
    
    referral_link = get_referral_link(query.from_user.id)
    
    full_text = text + f"\n\nSizning referral havolangiz:\n`{referral_link}`"
    
    share_url = f"https://t.me/share/url?url={referral_link}&text=Bu%20bot%20orqali%20pul%20ishlash%20mumkin!%20Keling%2C%20birga%20boshlaymiz."
    
    keyboard = [
        [InlineKeyboardButton("📱 BetWinner APK", callback_data="show_apk")],
        [InlineKeyboardButton("📤 Ulashish", url=share_url)],
        [InlineKeyboardButton("💸 Pul chiqarish", callback_data="withdraw")],
        [InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if photo_id:
        await query.edit_message_media(
            media=InputMediaPhoto(media=photo_id, caption=full_text, parse_mode="Markdown"),
            reply_markup=reply_markup
        )
    else:
        await query.edit_message_text(
            full_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = await ensure_user(user_id, query.from_user.username, query.from_user.first_name)
    balance = user_data.get("balance", 0)
    referrals = user_data.get("referrals", 0)
    text = (
        f"💵 *Sizning balansingiz:*\n\n"
        f"Balans: *{balance} so‘m*\n"
        f"Taklif qilgan do‘stlaringiz: *{referrals}*\n\n"
        f"Minimal yechish summasi: {MIN_WITHDRAW} so‘m."
    )
    keyboard = [
        [InlineKeyboardButton("💸 Pul chiqarish", callback_data="withdraw")],
        [InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")]
    ]
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pul chiqarish – kodni ko‘rsatadi va saytga yo‘naltiradi."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = await ensure_user(user_id, query.from_user.username, query.from_user.first_name)
    balance = user_data.get("balance", 0)

    if balance < MIN_WITHDRAW:
        await query.edit_message_text(
            f"❌ Pul chiqarish uchun minimal balans {MIN_WITHDRAW} so‘m. Sizda {balance} so‘m bor.",
            reply_markup=get_back_to_main_keyboard()
        )
        return

    code = user_data.get("withdraw_code")
    text = (
        f"💸 *Pul chiqarish*\n\n"
        f"Sizning maxsus 7 xonali kodingiz: `{code}`\n"
        f"Pul yechish uchun quyidagi tugma orqali saytga o‘ting va kodni kiriting.\n\n"
        f"Saytda kodni kiritib, pul yechishni tasdiqlang."
    )
    keyboard = [
        [InlineKeyboardButton("💳 Saytga o‘tish", url=WITHDRAW_SITE_URL)],
        [InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")]
    ]
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ------------------- ADMIN PANEL -------------------
# Conversation holatlari
ADD_NAME, ADD_TEXT, ADD_PHOTO, ADD_FILE, ADD_BUTTON_TEXT, ADD_BUTTON_URL = range(6)
EDIT_TEXT, EDIT_PHOTO, EDIT_FILE, EDIT_BUTTON_TEXT, EDIT_BUTTON_URL = range(6, 11)
APK_UPLOAD, APK_TEXT, APK_PHOTO = range(11, 14)
EARN_TEXT_EDIT = 14
BROADCAST_MSG = 15

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return
    await update.message.reply_text("👨‍💻 Admin paneli:", reply_markup=get_admin_keyboard())

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panelidagi callbacklarni boshqaradi."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return

    data = query.data

    if data == "admin_remove_list":
        if not games_data:
            await query.edit_message_text("Hech qanday o‘yin mavjud emas.")
            return
        await query.edit_message_text(
            "O‘chiriladigan kun stavkasini tanlang:",
            reply_markup=get_games_list_keyboard("remove_")
        )

    elif data == "admin_edit_list":
        if not games_data:
            await query.edit_message_text("Hech qanday o‘yin mavjud emas.")
            return
        await query.edit_message_text(
            "Tahrirlanadigan kun stavkasini tanlang:",
            reply_markup=get_games_list_keyboard("edit_")
        )

    elif data == "admin_stats":
        if not games_data:
            await query.edit_message_text("Statistika uchun maʼlumot yo‘q.")
            return
        lines = ["📊 Statistika (kun stavkalari):"]
        total = 0
        for name, game in games_data.items():
            views = game.get("views", 0)
            lines.append(f"• {name}: {views} marta ko‘rilgan")
            total += views
        lines.append(f"\nJami: {total} marta")
        await query.edit_message_text("\n".join(lines), reply_markup=get_admin_keyboard())
    
    elif data == "admin_users_count":
        total_users = len(users_data)
        active_users = sum(1 for u in users_data.values() if u.get("start_bonus_given", False))
        referred_users = sum(1 for u in users_data.values() if u.get("referred_by") is not None)
        total_balance = sum(u.get("balance", 0) for u in users_data.values())
        
        stats_text = (
            f"👥 *Foydalanuvchilar statistikasi*\n\n"
            f"📊 Umumiy foydalanuvchilar: *{total_users}*\n"
            f"✅ Faol foydalanuvchilar: *{active_users}*\n"
            f"🔗 Referral orqali kelganlar: *{referred_users}*\n"
            f"💰 Umumiy balans: *{total_balance} so‘m*"
        )
        await query.edit_message_text(
            stats_text,
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard()
        )

    elif data == "admin_apk_menu":
        await admin_apk_menu(update, context)

    elif data == "admin_earn_edit":
        await admin_earn_edit(update, context)

    elif data == "admin_close":
        await query.edit_message_text("Panel yopildi.")

    elif data == "admin_back":
        await query.edit_message_text("Admin paneli:", reply_markup=get_admin_keyboard())

    elif data.startswith("remove_"):
        game_name = data.replace("remove_", "")
        context.user_data["remove_game"] = game_name
        keyboard = [
            [InlineKeyboardButton("✅ Ha", callback_data="confirm_remove")],
            [InlineKeyboardButton("❌ Yo‘q", callback_data="admin_back")]
        ]
        await query.edit_message_text(
            f"'{game_name}' kun stavkasini o‘chirishni tasdiqlaysizmi?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "confirm_remove":
        game_name = context.user_data.get("remove_game")
        if game_name and game_name in games_data:
            del games_data[game_name]
            save_games(games_data)
            await query.edit_message_text(
                f"✅ '{game_name}' o‘chirildi.",
                reply_markup=get_admin_keyboard()
            )
        else:
            await query.edit_message_text("Xatolik yuz berdi.", reply_markup=get_admin_keyboard())

    elif data.startswith("edit_"):
        game_name = data.replace("edit_", "")
        context.user_data["edit_game"] = game_name
        keyboard = [
            [InlineKeyboardButton("✏️ Matn", callback_data=f"edit_text_{game_name}")],
            [InlineKeyboardButton("🖼 Rasm", callback_data=f"edit_photo_{game_name}")],
            [InlineKeyboardButton("📁 Fayl", callback_data=f"edit_file_{game_name}")],
            [InlineKeyboardButton("🔗 Tugma", callback_data=f"edit_button_{game_name}")],
            [InlineKeyboardButton("◀️ Back", callback_data="admin_back")]
        ]
        await query.edit_message_text(
            f"'{game_name}' – nimani tahrirlaysiz?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ------------------- ADMIN APK BOSHQARUVI -------------------
async def admin_apk_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return
    
    global apk_data
    status = "✅ APK mavjud" if apk_data.get("file_id") else "❌ APK mavjud emas"
    text = f"📱 *BetWinner APK boshqaruvi*\n\n{status}\n\nQuyidagi amallardan birini tanlang:"
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_apk_admin_keyboard()
    )

async def admin_apk_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return ConversationHandler.END
    
    await query.edit_message_text(
        "📤 *APK faylini yuboring:*\n\n"
        "Fayl format: .apk\n"
        "Bekor qilish uchun /cancel",
        parse_mode="Markdown"
    )
    return APK_UPLOAD

async def apk_upload_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return ConversationHandler.END
    
    global apk_data
    
    if update.message.document:
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name
        
        if not file_name.endswith('.apk'):
            await update.message.reply_text(
                "❌ Noto'g'ri format. Faqat .apk fayllar qabul qilinadi.\n"
                "Qayta urinib ko'ring yoki /cancel",
                reply_markup=get_admin_keyboard()
            )
            return APK_UPLOAD
        
        apk_data["file_id"] = file_id
        apk_data["version"] = file_name.replace('.apk', '')
        apk_data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_apk(apk_data)
        
        await update.message.reply_text(
            f"✅ APK fayli muvaffaqiyatli yuklandi!\n\nFayl: {file_name}",
            reply_markup=get_admin_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Iltimos, APK fayl yuboring.",
            reply_markup=get_admin_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def admin_apk_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return ConversationHandler.END
    
    await query.edit_message_text(
        "✏️ *APK uchun yangi matnni kiriting:*\n\n"
        "Hozirgi matn:\n" + apk_data.get("text", "Matn mavjud emas") + "\n\n"
        "Bekor qilish uchun /cancel",
        parse_mode="Markdown"
    )
    return APK_TEXT

async def apk_text_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return ConversationHandler.END
    
    global apk_data
    new_text = update.message.text
    apk_data["text"] = new_text
    save_apk(apk_data)
    
    await update.message.reply_text(
        "✅ APK matni yangilandi!",
        reply_markup=get_admin_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def admin_apk_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return ConversationHandler.END
    
    await query.edit_message_text(
        "🖼 *APK uchun rasm yuboring:*\n\n"
        "Rasm APK bo'limida ko'rsatiladi.\n"
        "Bekor qilish uchun /cancel",
        parse_mode="Markdown"
    )
    return APK_PHOTO

async def apk_photo_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return ConversationHandler.END
    
    global apk_data
    
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
        apk_data["photo_id"] = photo_id
        save_apk(apk_data)
        
        await update.message.reply_text(
            "✅ APK rasmi saqlandi!",
            reply_markup=get_admin_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Iltimos, rasm yuboring.",
            reply_markup=get_admin_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def admin_apk_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return
    
    global apk_data
    apk_data["file_id"] = None
    apk_data["version"] = "1.0.0"
    apk_data["updated_at"] = None
    save_apk(apk_data)
    
    await query.edit_message_text(
        "✅ APK fayli o'chirildi!",
        reply_markup=get_apk_admin_keyboard()
    )

# ------------------- ADMIN PUL ISHLASH MATNI -------------------
async def admin_earn_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return ConversationHandler.END
    
    global earn_data
    
    keyboard = [
        [InlineKeyboardButton("✏️ Matnni tahrirlash", callback_data="admin_earn_text")],
        [InlineKeyboardButton("🖼 Rasm qo'shish", callback_data="admin_earn_photo")],
        [InlineKeyboardButton("❌ Rasmni o'chirish", callback_data="admin_earn_photo_delete")],
        [InlineKeyboardButton("◀️ Admin panel", callback_data="admin_back")]
    ]
    
    status = "✅ Rasm mavjud" if earn_data.get("photo_id") else "❌ Rasm mavjud emas"
    text = f"💰 *BetWinner bilan pul ishlash matnini tahrirlash*\n\n{status}\n\nHozirgi matn:\n{earn_data['text']}"
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_earn_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return ConversationHandler.END
    
    await query.edit_message_text(
        "✏️ *Pul ishlash bo'limi uchun yangi matnni kiriting:*\n\n"
        "Matnni Markdown formatida yozishingiz mumkin.\n"
        "Bekor qilish uchun /cancel",
        parse_mode="Markdown"
    )
    return EARN_TEXT_EDIT

async def earn_text_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return ConversationHandler.END
    
    global earn_data
    new_text = update.message.text
    earn_data["text"] = new_text
    save_earn_text(earn_data)
    
    await update.message.reply_text(
        "✅ Pul ishlash matni yangilandi!",
        reply_markup=get_admin_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def admin_earn_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return ConversationHandler.END
    
    await query.edit_message_text(
        "🖼 *Pul ishlash bo'limi uchun rasm yuboring:*\n\n"
        "Rasm pul ishlash bo'limida ko'rsatiladi.\n"
        "Bekor qilish uchun /cancel",
        parse_mode="Markdown"
    )
    return EARN_TEXT_EDIT + 1

async def earn_photo_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return ConversationHandler.END
    
    global earn_data
    
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
        earn_data["photo_id"] = photo_id
        save_earn_text(earn_data)
        
        await update.message.reply_text(
            "✅ Pul ishlash rasmi saqlandi!",
            reply_markup=get_admin_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Iltimos, rasm yuboring.",
            reply_markup=get_admin_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def admin_earn_photo_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return
    
    global earn_data
    earn_data["photo_id"] = None
    save_earn_text(earn_data)
    
    await query.edit_message_text(
        "✅ Rasm o'chirildi!",
        reply_markup=get_admin_keyboard()
    )

# ------------------- ADD GAME -------------------
async def admin_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return ConversationHandler.END

    context.user_data.clear()
    context.user_data["add_game"] = {}
    await query.edit_message_text("Yangi kun stavkasi nomini kiriting (masalan: 'Futbol kuponlari'):")
    return ADD_NAME

async def add_game_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        name = update.message.text.strip()
        if not name:
            await update.message.reply_text("Nom bo‘sh bo‘lishi mumkin emas. Qayta kiriting:")
            return ADD_NAME
        if name in games_data:
            await update.message.reply_text("Bu nom allaqachon mavjud. Boshqa nom kiriting:")
            return ADD_NAME
        context.user_data["add_game"]["name"] = name
        await update.message.reply_text("Endi kun stavkasi matnini kiriting (HTML teglar bilan):")
        return ADD_TEXT
    except Exception as e:
        logger.error(f"add_game_name xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi. Qaytadan urinib ko‘ring.")
        return ConversationHandler.END

async def add_game_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        context.user_data["add_game"]["text"] = text
        await update.message.reply_text(
            "Matn saqlandi. Endi rasm yuboring (ixtiyoriy) yoki /skip ni bosing."
        )
        return ADD_PHOTO
    except Exception as e:
        logger.error(f"add_game_text xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def add_game_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.photo:
            photo_id = update.message.photo[-1].file_id
            context.user_data["add_game"]["photo_id"] = photo_id
            await update.message.reply_text("Rasm saqlandi. Endi fayl (APK) yuboring (ixtiyoriy) yoki /skip ni bosing.")
        else:
            await update.message.reply_text("Iltimos, rasm yuboring yoki /skip ni bosing.")
            return ADD_PHOTO
        return ADD_FILE
    except Exception as e:
        logger.error(f"add_game_photo xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def add_game_photo_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["add_game"]["photo_id"] = None
        await update.message.reply_text("Rasm o‘tkazib yuborildi. Endi fayl (APK) yuboring (ixtiyoriy) yoki /skip ni bosing.")
        return ADD_FILE
    except Exception as e:
        logger.error(f"add_game_photo_skip xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def add_game_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.document:
            file_id = update.message.document.file_id
            context.user_data["add_game"]["file_id"] = file_id
        else:
            context.user_data["add_game"]["file_id"] = None
        await update.message.reply_text(
            "Fayl saqlandi. Endi tugma matnini kiriting (ixtiyoriy) yoki /skip ni bosing.\n"
            "Masalan: '🎮 Kunlik kuponlarni olish'"
        )
        return ADD_BUTTON_TEXT
    except Exception as e:
        logger.error(f"add_game_file xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def add_game_file_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["add_game"]["file_id"] = None
        await update.message.reply_text(
            "Fayl o‘tkazib yuborildi. Endi tugma matnini kiriting (ixtiyoriy) yoki /skip ni bosing.\n"
            "Masalan: '🎮 Kunlik kuponlarni olish'"
        )
        return ADD_BUTTON_TEXT
    except Exception as e:
        logger.error(f"add_game_file_skip xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def add_game_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        button_text = update.message.text.strip()
        context.user_data["add_game"]["button_text"] = button_text
        await update.message.reply_text(
            "Tugma matni saqlandi. Endi tugma havolasini (URL) kiriting (ixtiyoriy) yoki /skip ni bosing.\n"
            "Masalan: https://example.com"
        )
        return ADD_BUTTON_URL
    except Exception as e:
        logger.error(f"add_game_button_text xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def add_game_button_text_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["add_game"]["button_text"] = None
        await update.message.reply_text(
            "Tugma matni o‘tkazib yuborildi. Endi tugma havolasini (URL) kiriting (ixtiyoriy) yoki /skip ni bosing."
        )
        return ADD_BUTTON_URL
    except Exception as e:
        logger.error(f"add_game_button_text_skip xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def add_game_button_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        button_url = update.message.text.strip()
        context.user_data["add_game"]["button_url"] = button_url
        game_data = context.user_data["add_game"]
        games_data[game_data["name"]] = {
            "text": game_data["text"],
            "photo_id": game_data.get("photo_id"),
            "file_id": game_data.get("file_id"),
            "button_text": game_data.get("button_text"),
            "button_url": game_data.get("button_url"),
            "views": 0
        }
        save_games(games_data)
        await update.message.reply_text(
            f"✅ '{game_data['name']}' kun stavkasi qo‘shildi!",
            reply_markup=get_admin_keyboard()
        )
        context.user_data.pop("add_game", None)
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"add_game_button_url xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def add_game_button_url_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["add_game"]["button_url"] = None
        game_data = context.user_data["add_game"]
        games_data[game_data["name"]] = {
            "text": game_data["text"],
            "photo_id": game_data.get("photo_id"),
            "file_id": game_data.get("file_id"),
            "button_text": game_data.get("button_text"),
            "button_url": None,
            "views": 0
        }
        save_games(games_data)
        await update.message.reply_text(
            f"✅ '{game_data['name']}' kun stavkasi qo‘shildi!",
            reply_markup=get_admin_keyboard()
        )
        context.user_data.pop("add_game", None)
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"add_game_button_url_skip xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def add_game_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Qo‘shish bekor qilindi.", reply_markup=get_admin_keyboard())
    return ConversationHandler.END

# ------------------- EDIT GAME -------------------
async def edit_text_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("edit_text_"):
        game_name = data.replace("edit_text_", "")
    else:
        game_name = context.user_data.get("edit_game")
        if not game_name:
            await query.edit_message_text("Xatolik: kun stavkasi nomi topilmadi.")
            return ConversationHandler.END
    context.user_data.clear()
    context.user_data["edit_game"] = game_name
    await query.edit_message_text("Yangi matnni kiriting (HTML teglar bilan):")
    return EDIT_TEXT

async def edit_game_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        game_name = context.user_data["edit_game"]
        new_text = update.message.text
        games_data[game_name]["text"] = new_text
        save_games(games_data)
        await update.message.reply_text(f"✅ Matn yangilandi.", reply_markup=get_admin_keyboard())
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"edit_game_text xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def edit_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("edit_photo_"):
        game_name = data.replace("edit_photo_", "")
    else:
        game_name = context.user_data.get("edit_game")
        if not game_name:
            await query.edit_message_text("Xatolik: kun stavkasi nomi topilmadi.")
            return ConversationHandler.END
    context.user_data.clear()
    context.user_data["edit_game"] = game_name
    await query.edit_message_text("Yangi rasmni yuboring:")
    return EDIT_PHOTO

async def edit_game_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.photo:
            photo_id = update.message.photo[-1].file_id
            game_name = context.user_data["edit_game"]
            games_data[game_name]["photo_id"] = photo_id
            save_games(games_data)
            await update.message.reply_text(f"✅ Rasm yangilandi.", reply_markup=get_admin_keyboard())
            context.user_data.clear()
            return ConversationHandler.END
        else:
            await update.message.reply_text("Iltimos, rasm yuboring.")
            return EDIT_PHOTO
    except Exception as e:
        logger.error(f"edit_game_photo xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def edit_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("edit_file_"):
        game_name = data.replace("edit_file_", "")
    else:
        game_name = context.user_data.get("edit_game")
        if not game_name:
            await query.edit_message_text("Xatolik: kun stavkasi nomi topilmadi.")
            return ConversationHandler.END
    context.user_data.clear()
    context.user_data["edit_game"] = game_name
    await query.edit_message_text("Yangi faylni yuboring:")
    return EDIT_FILE

async def edit_game_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.document:
            file_id = update.message.document.file_id
            game_name = context.user_data["edit_game"]
            games_data[game_name]["file_id"] = file_id
            save_games(games_data)
            await update.message.reply_text(f"✅ Fayl yangilandi.", reply_markup=get_admin_keyboard())
            context.user_data.clear()
            return ConversationHandler.END
        else:
            await update.message.reply_text("Iltimos, fayl yuboring.")
            return EDIT_FILE
    except Exception as e:
        logger.error(f"edit_game_file xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def edit_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("edit_button_"):
        game_name = data.replace("edit_button_", "")
    else:
        game_name = context.user_data.get("edit_game")
        if not game_name:
            await query.edit_message_text("Xatolik: kun stavkasi nomi topilmadi.")
            return ConversationHandler.END
    context.user_data.clear()
    context.user_data["edit_game"] = game_name
    await query.edit_message_text("Yangi tugma matnini kiriting (ixtiyoriy, /skip):")
    return EDIT_BUTTON_TEXT

async def edit_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        button_text = update.message.text.strip()
        context.user_data["edit_button_text"] = button_text
        await update.message.reply_text(
            "Tugma matni saqlandi. Endi tugma havolasini (URL) kiriting (ixtiyoriy, /skip):"
        )
        return EDIT_BUTTON_URL
    except Exception as e:
        logger.error(f"edit_button_text xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def edit_button_text_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["edit_button_text"] = None
        await update.message.reply_text("Tugma matni o‘tkazib yuborildi. Endi tugma havolasini (URL) kiriting (ixtiyoriy, /skip):")
        return EDIT_BUTTON_URL
    except Exception as e:
        logger.error(f"edit_button_text_skip xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def edit_button_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        button_url = update.message.text.strip()
        game_name = context.user_data["edit_game"]
        button_text = context.user_data.get("edit_button_text")
        games_data[game_name]["button_text"] = button_text
        games_data[game_name]["button_url"] = button_url
        save_games(games_data)
        await update.message.reply_text(f"✅ Tugma maʼlumotlari yangilandi.", reply_markup=get_admin_keyboard())
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"edit_button_url xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def edit_button_url_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        game_name = context.user_data["edit_game"]
        button_text = context.user_data.get("edit_button_text")
        games_data[game_name]["button_text"] = button_text
        games_data[game_name]["button_url"] = None
        save_games(games_data)
        await update.message.reply_text(f"✅ Tugma maʼlumotlari yangilandi (faqat matn).", reply_markup=get_admin_keyboard())
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"edit_button_url_skip xatosi: {traceback.format_exc()}")
        await update.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END

async def edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Tahrirlash bekor qilindi.", reply_markup=get_admin_keyboard())
    return ConversationHandler.END

# ------------------- BROADCAST -------------------
async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Siz admin emassiz.")
        return ConversationHandler.END

    await query.edit_message_text(
        "📨 *Barchaga yuboriladigan xabarni kiriting:*\n\n"
        "Matn, rasm, video yoki fayl bo‘lishi mumkin.\n"
        "Bekor qilish uchun /cancel buyrug'ini bosing.",
        parse_mode="Markdown"
    )
    return BROADCAST_MSG

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return ConversationHandler.END

    message = update.message
    success_count = 0
    fail_count = 0
    
    status_msg = await update.message.reply_text(
        f"📨 Xabar yuborilmoqda...\n"
        f"Jami foydalanuvchilar: {len(users_data)}"
    )

    for user_id_str in users_data.keys():
        try:
            user_id = int(user_id_str)
            
            if message.text:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message.text,
                    parse_mode="HTML" if message.text else None
                )
            elif message.photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=message.photo[-1].file_id,
                    caption=message.caption,
                    parse_mode="HTML" if message.caption else None
                )
            elif message.video:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=message.video.file_id,
                    caption=message.caption,
                    parse_mode="HTML" if message.caption else None
                )
            elif message.document:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=message.document.file_id,
                    caption=message.caption,
                    parse_mode="HTML" if message.caption else None
                )
            
            success_count += 1
            
            if (success_count + fail_count) % 10 == 0:
                await status_msg.edit_text(
                    f"📨 Xabar yuborilmoqda...\n"
                    f"✅ Yuborildi: {success_count}\n"
                    f"❌ Yuborilmadi: {fail_count}\n"
                    f"Jami: {len(users_data)}"
                )
                
        except Exception as e:
            fail_count += 1
            logger.error(f"Xabar yuborishda xatolik (user {user_id_str}): {e}")

    await status_msg.edit_text(
        f"📨 *Xabar yuborish yakunlandi!*\n\n"
        f"✅ Muvaffaqiyatli: *{success_count}*\n"
        f"❌ Muvaffaqiyatsiz: *{fail_count}*\n"
        f"👥 Jami foydalanuvchilar: *{len(users_data)}*",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Xabar yuborish bekor qilindi.",
        reply_markup=get_admin_keyboard()
    )
    return ConversationHandler.END

# ------------------- MAIN -------------------
def main():
    app = Application.builder().token(TOKEN).build()

    # Asosiy handlerlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    
    # Callback handlerlar
    app.add_handler(CallbackQueryHandler(show_games, pattern="^show_games$"))
    app.add_handler(CallbackQueryHandler(show_apk, pattern="^show_apk$"))
    app.add_handler(CallbackQueryHandler(download_apk, pattern="^download_apk$"))
    app.add_handler(CallbackQueryHandler(game_callback, pattern="^game_"))
    app.add_handler(CallbackQueryHandler(earn_callback, pattern="^earn$"))
    app.add_handler(CallbackQueryHandler(balance_callback, pattern="^balance$"))
    app.add_handler(CallbackQueryHandler(withdraw_callback, pattern="^withdraw$"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^main_menu$"))
    
    # Admin callbacklar
    app.add_handler(CallbackQueryHandler(
        admin_callback_handler,
        pattern="^(admin_remove_list|admin_edit_list|admin_stats|admin_users_count|admin_apk_menu|admin_earn_edit|admin_apk_upload|admin_apk_text|admin_apk_photo|admin_apk_delete|admin_close|admin_back|remove_|confirm_remove|edit_text_|edit_photo_|edit_file_|edit_button_|admin_earn_text|admin_earn_photo|admin_earn_photo_delete)$"
    ))

    # ADD GAME conversation
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_callback, pattern="^admin_add$")],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_name)],
            ADD_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_text)],
            ADD_PHOTO: [
                MessageHandler(filters.PHOTO, add_game_photo),
                CommandHandler("skip", add_game_photo_skip)
            ],
            ADD_FILE: [
                MessageHandler(filters.Document.ALL, add_game_file),
                CommandHandler("skip", add_game_file_skip)
            ],
            ADD_BUTTON_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_button_text),
                CommandHandler("skip", add_game_button_text_skip)
            ],
            ADD_BUTTON_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_button_url),
                CommandHandler("skip", add_game_button_url_skip)
            ],
        },
        fallbacks=[CommandHandler("cancel", add_game_cancel)],
    )
    app.add_handler(add_conv)

    # EDIT GAME conversations
    edit_text_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_text_callback, pattern="^edit_text_")],
        states={EDIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_game_text)]},
        fallbacks=[CommandHandler("cancel", edit_cancel)],
    )
    app.add_handler(edit_text_conv)

    edit_photo_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_photo_callback, pattern="^edit_photo_")],
        states={EDIT_PHOTO: [MessageHandler(filters.PHOTO, edit_game_photo)]},
        fallbacks=[CommandHandler("cancel", edit_cancel)],
    )
    app.add_handler(edit_photo_conv)

    edit_file_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_file_callback, pattern="^edit_file_")],
        states={EDIT_FILE: [MessageHandler(filters.Document.ALL, edit_game_file)]},
        fallbacks=[CommandHandler("cancel", edit_cancel)],
    )
    app.add_handler(edit_file_conv)

    edit_button_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_button_callback, pattern="^edit_button_")],
        states={
            EDIT_BUTTON_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_button_text),
                CommandHandler("skip", edit_button_text_skip)
            ],
            EDIT_BUTTON_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_button_url),
                CommandHandler("skip", edit_button_url_skip)
            ],
        },
        fallbacks=[CommandHandler("cancel", edit_cancel)],
    )
    app.add_handler(edit_button_conv)

    # APK conversations
    apk_upload_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_apk_upload, pattern="^admin_apk_upload$")],
        states={APK_UPLOAD: [MessageHandler(filters.Document.ALL, apk_upload_file)]},
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    app.add_handler(apk_upload_conv)

    apk_text_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_apk_text, pattern="^admin_apk_text$")],
        states={APK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, apk_text_save)]},
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    app.add_handler(apk_text_conv)

    apk_photo_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_apk_photo, pattern="^admin_apk_photo$")],
        states={APK_PHOTO: [MessageHandler(filters.PHOTO, apk_photo_save)]},
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    app.add_handler(apk_photo_conv)

    # EARN conversations
    earn_text_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_earn_text, pattern="^admin_earn_text$")],
        states={EARN_TEXT_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, earn_text_save)]},
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    app.add_handler(earn_text_conv)

    earn_photo_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_earn_photo, pattern="^admin_earn_photo$")],
        states={EARN_TEXT_EDIT + 1: [MessageHandler(filters.PHOTO, earn_photo_save)]},
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    app.add_handler(earn_photo_conv)

    # BROADCAST conversation
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_callback, pattern="^admin_broadcast$")],
        states={BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_message)]},
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    app.add_handler(broadcast_conv)

    logger.info("✅ Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
