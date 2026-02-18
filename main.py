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
BOT_USERNAME = "BETWINNERplay_bot"  # Bot username (@ belgisisiz)
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
        logger.info(f"✅ Yangi foydalanuvchi: {user_id}")
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
        
        # Referral kod orqali taklif qiluvchini topish
        referrer_id = None
        for uid, data in users_data.items():
            if data.get("referral_code") == referral_code and uid != str(user_id):
                referrer_id = uid
                break
        
        # Agar taklif qiluvchi topilsa va bu foydalanuvchi hali taklif qilinmagan bo'lsa
        if referrer_id and not user_data.get("referred_by"):
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
                        f"🎉 Sizning taklifingiz orqali yangi foydalanuvchi qo‘shildi!\n\n"
                        f"👤 {referrer_name}\n"
                        f"💰 Balansingizga {REFERRAL_BONUS} so‘m qo‘shildi.\n"
                        f"💵 Hozirgi balans: {users_data[referrer_id]['balance']} so‘m"
                    )
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
    """APK tugmasi bosilganda to'g'ridan-to'g'ri APK fayl yuboriladi"""
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
        await query.message.reply_text(
            "❌ Hozircha APK fayli mavjud emas. Tez orada yuklanadi!",
            reply_markup=get_back_keyboard()
        )

# ------------------- PUL ISHLASH VA BALANS -------------------
async def earn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    referral_link = get_referral_link(user_id)
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

# ------------------- ADMIN BUYRUQLARI -------------------
# /newapk - APK yuklash
async def newapk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return
    
    await update.message.reply_text("📤 APK faylini yuboring (.apk formatida):")
    context.user_data['waiting_for'] = 'apk'

# /deleteapk - APK ni o'chirish
async def deleteapk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return
    
    apk_data['file_id'] = None
    save_apk(apk_data)
    await update.message.reply_text("✅ APK o'chirildi!")

# /newkupon - Yangi kupon qo'shish
async def newkupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return
    
    await update.message.reply_text("Kupon nomini kiriting:")
    context.user_data['waiting_for'] = 'kupon_name'

# /deletekupon - Kuponni o'chirish
async def deletekupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return
    
    if not games_data:
        await update.message.reply_text("Hech qanday kupon mavjud emas.")
        return
    
    text = "O'chiriladigan kuponni tanlang:\n\n"
    for game in games_data.keys():
        text += f"• {game}\n"
    text += "\nKupon nomini yozib yuboring:"
    
    await update.message.reply_text(text)
    context.user_data['waiting_for'] = 'delete_kupon'

# /new - Barchaga xabar yuborish
async def new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Siz admin emassiz.")
        return
    
    await update.message.reply_text("📨 Barchaga yuboriladigan xabarni kiriting (matn yoki rasm):")
    context.user_data['waiting_for'] = 'broadcast'

# ------------------- XABARLARNI QABUL QILISH -------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    waiting_for = context.user_data.get('waiting_for')
    
    # APK yuklash
    if waiting_for == 'apk':
        if update.message.document and update.message.document.file_name.endswith('.apk'):
            file_id = update.message.document.file_id
            apk_data['file_id'] = file_id
            save_apk(apk_data)
            await update.message.reply_text("✅ APK yuklandi!")
        else:
            await update.message.reply_text("❌ .apk fayl yuboring!")
        context.user_data.clear()
    
    # Kupon nomi
    elif waiting_for == 'kupon_name':
        context.user_data['kupon_name'] = update.message.text
        await update.message.reply_text("Kupon matnini kiriting:")
        context.user_data['waiting_for'] = 'kupon_text'
    
    # Kupon matni
    elif waiting_for == 'kupon_text':
        context.user_data['kupon_text'] = update.message.text
        await update.message.reply_text("Rasm yuboring (ixtiyoriy, /skip):")
        context.user_data['waiting_for'] = 'kupon_photo'
    
    # Kupon rasmi
    elif waiting_for == 'kupon_photo':
        name = context.user_data['kupon_name']
        text = context.user_data['kupon_text']
        photo_id = None
        
        if update.message.photo:
            photo_id = update.message.photo[-1].file_id
        
        games_data[name] = {
            'text': text,
            'photo_id': photo_id,
            'views': 0
        }
        save_games(games_data)
        await update.message.reply_text(f"✅ '{name}' kuponi qo'shildi!")
        context.user_data.clear()
    
    # Kupon o'chirish
    elif waiting_for == 'delete_kupon':
        name = update.message.text.strip()
        if name in games_data:
            del games_data[name]
            save_games(games_data)
            await update.message.reply_text(f"✅ '{name}' kuponi o'chirildi!")
        else:
            await update.message.reply_text("❌ Bunday kupon topilmadi!")
        context.user_data.clear()
    
    # Broadcast
    elif waiting_for == 'broadcast':
        message = update.message
        success = 0
        fail = 0
        
        status = await update.message.reply_text("📨 Xabar yuborilmoqda...")
        
        for user_id_str in users_data.keys():
            try:
                if message.text:
                    await context.bot.send_message(chat_id=int(user_id_str), text=message.text)
                elif message.photo:
                    await context.bot.send_photo(
                        chat_id=int(user_id_str),
                        photo=message.photo[-1].file_id,
                        caption=message.caption
                )
                success += 1
            except:
                fail += 1
        
        await status.edit_text(f"✅ Yuborildi: {success}\n❌ Yuborilmadi: {fail}")
        await update.message.reply_text("✅ Broadcast tugadi!")
        context.user_data.clear()

# ------------------- SKIP -------------------
async def skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    if context.user_data.get('waiting_for') == 'kupon_photo':
        name = context.user_data['kupon_name']
        text = context.user_data['kupon_text']
        
        games_data[name] = {
            'text': text,
            'photo_id': None,
            'views': 0
        }
        save_games(games_data)
        await update.message.reply_text(f"✅ '{name}' kuponi qo'shildi!")
        context.user_data.clear()
    else:
        await update.message.reply_text("Bekor qilindi.")
        context.user_data.clear()

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
