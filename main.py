import json
import logging
import os
import asyncio
import random
import traceback
from pathlib import Path
from typing import Dict
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# ------------------- SOZLAMALAR -------------------
TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = 6935090105  # Admin Telegram ID
MONGODB_URI = os.environ.get("MONGODB_URI")

# Fayl yo'llari
DATA_FILE = "games.json"
USERS_FILE = "users.json"
APK_FILE = "apk.json"

REFERRAL_BONUS = 2500
START_BONUS = 15000
MIN_WITHDRAW = 25000
BOT_USERNAME = "Winwin_premium_bonusbot"
WITHDRAW_SITE_URL = "https://futbolinsidepulyechish.netlify.app/"

# ------------------- LOGLASH -------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------- MONGODB ULANISH -------------------
try:
    from pymongo import MongoClient
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False

if MONGODB_URI and MONGO_AVAILABLE:
    try:
        client = MongoClient(MONGODB_URI)
        db = client['betwinner_bot']
        users_collection = db['users']
        games_collection = db['games']
        apk_collection = db['apk']
        USE_MONGO = True
        logger.info("✅ MongoDB ga ulandi!")
    except:
        USE_MONGO = False
else:
    USE_MONGO = False

# ------------------- MAʼLUMOTLAR SAQLASH -------------------
def load_games() -> Dict:
    if USE_MONGO:
        games = {}
        for doc in games_collection.find():
            games[doc['name']] = {
                'text': doc.get('text', ''),
                'photo_id': doc.get('photo_id'),
                'views': doc.get('views', 0)
            }
        return games
    if Path(DATA_FILE).exists():
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_games(games: Dict):
    if USE_MONGO:
        for name, game_data in games.items():
            games_collection.update_one(
                {'name': name},
                {'$set': {
                    'name': name,
                    'text': game_data.get('text', ''),
                    'photo_id': game_data.get('photo_id'),
                    'views': game_data.get('views', 0)
                }},
                upsert=True
            )
    with open(DATA_FILE, "w") as f:
        json.dump(games, f)

def load_users() -> Dict:
    if USE_MONGO:
        users = {}
        for doc in users_collection.find():
            users[str(doc['user_id'])] = {
                'balance': doc.get('balance', 0),
                'referred_by': doc.get('referred_by'),
                'referrals': doc.get('referrals', 0),
                'start_bonus_given': doc.get('start_bonus_given', False),
                'withdraw_code': doc.get('withdraw_code')
            }
        return users
    if Path(USERS_FILE).exists():
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users: Dict):
    if USE_MONGO:
        for user_id_str, user_data in users.items():
            users_collection.update_one(
                {'user_id': int(user_id_str)},
                {'$set': {
                    'user_id': int(user_id_str),
                    'balance': user_data.get('balance', 0),
                    'referred_by': user_data.get('referred_by'),
                    'referrals': user_data.get('referrals', 0),
                    'start_bonus_given': user_data.get('start_bonus_given', False),
                    'withdraw_code': user_data.get('withdraw_code')
                }},
                upsert=True
            )
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

def load_apk() -> Dict:
    if USE_MONGO:
        doc = apk_collection.find_one({'_id': 'apk_config'})
        if doc:
            return {
                'file_id': doc.get('file_id'),
                'text': doc.get('text', '📱 BetWinner APK dasturini yuklab oling!'),
            }
    if Path(APK_FILE).exists():
        with open(APK_FILE, "r") as f:
            return json.load(f)
    return {"file_id": None, "text": "📱 BetWinner APK dasturini yuklab oling!"}

def save_apk(apk_data: Dict):
    if USE_MONGO:
        apk_collection.update_one(
            {'_id': 'apk_config'},
            {'$set': {
                '_id': 'apk_config',
                'file_id': apk_data.get('file_id'),
                'text': apk_data.get('text')
            }},
            upsert=True
        )
    with open(APK_FILE, "w") as f:
        json.dump(apk_data, f)

games_data = load_games()
users_data = load_users()
apk_data = load_apk()

# ------------------- YORDAMCHI FUNKSIYALAR -------------------
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def generate_unique_code() -> str:
    while True:
        code = f"{random.randint(0, 9999999):07d}"
        existing = [u.get("withdraw_code") for u in users_data.values() if u.get("withdraw_code")]
        if code not in existing:
            return code

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
    keyboard = [[InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")]]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Admin panel tugmalari"""
    keyboard = [
        [InlineKeyboardButton("➕ Yangi kun stavkasi qo'shish", callback_data="admin_add_game")],
        [InlineKeyboardButton("📤 APK yuklash", callback_data="admin_upload_apk")],
        [InlineKeyboardButton("📨 Barchaga xabar yuborish", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("❌ Panelni yopish", callback_data="admin_close")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_games_keyboard() -> InlineKeyboardMarkup:
    """Kun stavkalari ro'yxati"""
    keyboard = []
    for game in games_data.keys():
        keyboard.append([InlineKeyboardButton(game, callback_data=f"game_{game}")])
    keyboard.append([InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

async def ensure_user(user_id: int, username: str = None, first_name: str = None) -> dict:
    user_id_str = str(user_id)
    if user_id_str not in users_data:
        users_data[user_id_str] = {
            "balance": 0,
            "referred_by": None,
            "referrals": 0,
            "start_bonus_given": False,
            "withdraw_code": generate_unique_code(),
            "username": username,
            "first_name": first_name
        }
        save_users(users_data)
    return users_data[user_id_str]

async def give_start_bonus(user_id: int, context: ContextTypes.DEFAULT_TYPE):
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
    """Start komandasi – eski holatidagidek"""
    user = update.effective_user
    user_id = user.id
    args = context.args

    user_data = await ensure_user(user_id, user.username, user.first_name)

    # Referralni tekshirish
    if args and args[0].startswith("ref_"):
        try:
            ref_user_id = int(args[0].replace("ref_", ""))
            if ref_user_id != user_id and str(ref_user_id) in users_data and not user_data.get("referred_by"):
                user_data["referred_by"] = ref_user_id
                users_data[str(ref_user_id)]["balance"] += REFERRAL_BONUS
                users_data[str(ref_user_id)]["referrals"] += 1
                save_users(users_data)
                try:
                    await context.bot.send_message(
                        chat_id=ref_user_id,
                        text=f"🎉 Sizning taklifingiz orqali yangi foydalanuvchi qo‘shildi! Balansingizga {REFERRAL_BONUS} so‘m qo‘shildi."
                    )
                except:
                    pass
        except:
            pass

    # Start bonusini rejalashtirish
    if not user_data.get("start_bonus_given", False):
        asyncio.create_task(give_start_bonus(user_id, context))

    # Eski start xabari
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

# ------------------- KUN STAVKASI -------------------
async def show_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not games_data:
        await query.message.reply_text(
            "Hozircha kunlik stavkalar mavjud emas. Tez orada yangilanadi!",
            reply_markup=get_back_keyboard()
        )
        return
    await query.message.reply_text(
        "📊 *Bugungi kun stavkalari:*",
        parse_mode="Markdown",
        reply_markup=get_games_keyboard()
    )

async def game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    game_name = query.data.replace("game_", "")
    game = games_data.get(game_name)
    if not game:
        await query.message.reply_text("Bu kun stavkasi topilmadi.", reply_markup=get_back_keyboard())
        return

    game["views"] = game.get("views", 0) + 1
    save_games(games_data)

    text = game.get("text", "Maʼlumot hozircha kiritilmagan.")
    photo_id = game.get("photo_id")

    if photo_id:
        await query.message.reply_photo(
            photo=photo_id,
            caption=text,
            parse_mode="HTML",
            reply_markup=get_back_keyboard()
        )
    else:
        await query.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=get_back_keyboard()
        )

# ------------------- APK -------------------
async def show_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = apk_data.get("text", "📱 BetWinner APK dasturini yuklab oling!")
    file_id = apk_data.get("file_id")
    
    if file_id:
        keyboard = [
            [InlineKeyboardButton("📥 APK yuklash", callback_data="download_apk")],
            [InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")]
        ]
        await query.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.message.reply_text(
            "❌ Hozircha APK fayli mavjud emas. Tez orada yuklanadi!",
            reply_markup=get_back_keyboard()
        )

async def download_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    file_id = apk_data.get("file_id")
    if file_id:
        await query.message.reply_document(
            document=file_id,
            caption="📱 BetWinner APK",
            reply_markup=get_back_keyboard()
        )
    else:
        await query.message.reply_text("❌ APK fayli mavjud emas.", reply_markup=get_back_keyboard())

# ------------------- PUL ISHLASH VA BALANS -------------------
async def earn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    referral_link = get_referral_link(query.from_user.id)
    share_url = f"https://t.me/share/url?url={referral_link}&text=Bu%20bot%20orqali%20pul%20ishlash%20mumkin!%20Keling%2C%20birga%20boshlaymiz."
    
    text = (
        "💰 *BetWinner bilan qanday qilib pul ishlash mumkin?*\n\n"
        f"1️⃣ Do‘stlaringizni taklif qiling va har bir taklif uchun *{REFERRAL_BONUS} so‘m* oling.\n"
        f"2️⃣ Start bonus sifatida *{START_BONUS} so‘m* hamyoningizga tushadi.\n"
        f"3️⃣ Minimal yechish summasi: *{MIN_WITHDRAW} so‘m*.\n\n"
        f"Sizning referral havolangiz:\n`{referral_link}`"
    )
    
    keyboard = [
        [InlineKeyboardButton("📤 Ulashish", url=share_url)],
        [InlineKeyboardButton("💸 Pul chiqarish", callback_data="withdraw")],
        [InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")]
    ]
    await query.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = await ensure_user(query.from_user.id)
    
    text = (
        f"💵 *Sizning balansingiz:*\n\n"
        f"Balans: *{user_data['balance']} so‘m*\n"
        f"Taklif qilgan do‘stlaringiz: *{user_data['referrals']}*\n\n"
        f"Minimal yechish summasi: {MIN_WITHDRAW} so‘m."
    )
    keyboard = [
        [InlineKeyboardButton("💸 Pul chiqarish", callback_data="withdraw")],
        [InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")]
    ]
    await query.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = await ensure_user(query.from_user.id)
    
    if user_data['balance'] < MIN_WITHDRAW:
        await query.message.reply_text(
            f"❌ Pul chiqarish uchun minimal balans {MIN_WITHDRAW} so‘m. Sizda {user_data['balance']} so‘m bor.",
            reply_markup=get_back_keyboard()
        )
        return
    
    text = (
        f"💸 *Pul chiqarish*\n\n"
        f"Sizning maxsus 7 xonali kodingiz: `{user_data['withdraw_code']}`\n"
        f"Pul yechish uchun quyidagi tugma orqali saytga o‘ting va kodni kiriting."
    )
    keyboard = [
        [InlineKeyboardButton("💳 Saytga o‘tish", url=WITHDRAW_SITE_URL)],
        [InlineKeyboardButton("◀️ Bosh menyu", callback_data="main_menu")]
    ]
    await query.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ------------------- ADMIN PANEL -------------------
ADD_NAME, ADD_TEXT, ADD_PHOTO = range(3)
APK_UPLOAD = 3
BROADCAST_MSG = 4

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return
    await update.message.reply_text("👨‍💻 Admin paneli:", reply_markup=get_admin_keyboard())

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.message.reply_text("Siz admin emassiz.")
        return

    data = query.data
    logger.info(f"Admin callback: {data}")

    if data == "admin_add_game":
        context.user_data.clear()
        await query.message.reply_text("Yangi kun stavkasi nomini kiriting (masalan: 'Futbol kuponlari'):")
        return ADD_NAME

    elif data == "admin_upload_apk":
        context.user_data.clear()
        await query.message.reply_text("📤 APK faylini yuboring (.apk formatida):")
        return APK_UPLOAD

    elif data == "admin_broadcast":
        context.user_data.clear()
        await query.message.reply_text("📨 Barchaga yuboriladigan xabarni kiriting (matn yoki rasm):")
        return BROADCAST_MSG

    elif data == "admin_stats":
        total_users = len(users_data)
        total_games = len(games_data)
        total_views = sum(g.get('views', 0) for g in games_data.values())
        total_balance = sum(u.get('balance', 0) for u in users_data.values())
        
        text = (
            f"📊 *Statistika*\n\n"
            f"👥 Foydalanuvchilar: *{total_users}*\n"
            f"🎮 Kun stavkalari: *{total_games}*\n"
            f"👀 Ko'rishlar: *{total_views}*\n"
            f"💰 Umumiy balans: *{total_balance} so'm*"
        )
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

    elif data == "admin_close":
        await query.message.reply_text("Panel yopildi.", reply_markup=get_main_keyboard())

# ------------------- ADD GAME -------------------
async def add_game_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Nom bo‘sh bo‘lishi mumkin emas. Qayta kiriting:")
        return ADD_NAME
    if name in games_data:
        await update.message.reply_text("Bu nom allaqachon mavjud. Boshqa nom kiriting:")
        return ADD_NAME
    
    context.user_data['game_name'] = name
    await update.message.reply_text("Endi kun stavkasi matnini kiriting (HTML teglar bilan):")
    return ADD_TEXT

async def add_game_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['game_text'] = update.message.text
    await update.message.reply_text("Rasm yuboring (ixtiyoriy) yoki /skip ni bosing:")
    return ADD_PHOTO

async def add_game_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_id = None
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    
    games_data[context.user_data['game_name']] = {
        'text': context.user_data['game_text'],
        'photo_id': photo_id,
        'views': 0
    }
    save_games(games_data)
    await update.message.reply_text(
        f"✅ '{context.user_data['game_name']}' kun stavkasi qo‘shildi!",
        reply_markup=get_admin_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def add_game_photo_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    games_data[context.user_data['game_name']] = {
        'text': context.user_data['game_text'],
        'photo_id': None,
        'views': 0
    }
    save_games(games_data)
    await update.message.reply_text(
        f"✅ '{context.user_data['game_name']}' kun stavkasi qo‘shildi!",
        reply_markup=get_admin_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

# ------------------- APK UPLOAD -------------------
async def apk_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        file_name = update.message.document.file_name
        file_id = update.message.document.file_id
        
        if file_name.endswith('.apk'):
            apk_data['file_id'] = file_id
            save_apk(apk_data)
            await update.message.reply_text(
                f"✅ APK fayli muvaffaqiyatli yuklandi!\n\nFayl: {file_name}",
                reply_markup=get_admin_keyboard()
            )
            context.user_data.clear()
            return ConversationHandler.END
        else:
            await update.message.reply_text("❌ Noto'g'ri format. Faqat .apk fayllar qabul qilinadi. Qayta urinib ko'ring:")
            return APK_UPLOAD
    else:
        await update.message.reply_text("❌ Iltimos, APK fayl yuboring:")
        return APK_UPLOAD

# ------------------- BROADCAST -------------------
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    success = 0
    fail = 0
    
    status_msg = await update.message.reply_text("📨 Xabar yuborilmoqda...")
    
    for user_id_str in users_data.keys():
        try:
            user_id = int(user_id_str)
            
            if message.text:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message.text,
                    parse_mode="HTML"
                )
            elif message.photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=message.photo[-1].file_id,
                    caption=message.caption,
                    parse_mode="HTML" if message.caption else None
                )
            success += 1
        except Exception as e:
            fail += 1
            logger.error(f"Xatolik {user_id_str}: {e}")
    
    await status_msg.edit_text(
        f"📨 *Xabar yuborish yakunlandi!*\n\n"
        f"✅ Muvaffaqiyatli: *{success}*\n"
        f"❌ Muvaffaqiyatsiz: *{fail}*",
        parse_mode="Markdown"
    )
    await update.message.reply_text("✅ Broadcast tugadi!", reply_markup=get_admin_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=get_admin_keyboard())
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
    
    # Admin callback
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))

    # Add Game conversation
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^admin_add_game$")],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_name)],
            ADD_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_game_text)],
            ADD_PHOTO: [
                MessageHandler(filters.PHOTO, add_game_photo),
                CommandHandler("skip", add_game_photo_skip)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(add_conv)

    # APK upload conversation
    apk_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^admin_upload_apk$")],
        states={
            APK_UPLOAD: [MessageHandler(filters.Document.ALL, apk_upload)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(apk_conv)

    # Broadcast conversation
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern="^admin_broadcast$")],
        states={
            BROADCAST_MSG: [
                MessageHandler(filters.TEXT, broadcast_message),
                MessageHandler(filters.PHOTO, broadcast_message)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(broadcast_conv)

    logger.info("✅ Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
