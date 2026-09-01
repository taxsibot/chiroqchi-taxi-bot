from aiogram import Router, F, types
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from database.db import (
    get_user, add_user, add_driver_details, get_setting, 
    get_user_language, update_user_language, mark_user_started, 
    get_order, get_driver, delete_user, update_user_balance
)
from utils.states import Registration
from keyboards.reply import get_role_keyboard, get_phone_keyboard, get_driver_menu, get_language_keyboard, get_passenger_menu, get_secondary_phone_keyboard
from config import ADMIN_ID
from utils.locales import get_trans, TRANSLATIONS

from utils.utils import check_subscription, get_subscription_keyboard, IsMenuButton
from utils.ocr_helper import extract_plate_number, validate_uzb_plate, normalize_plate, normalize_for_comparison, reader
from utils.phone_validation import is_uzbek_number, normalize_phone
from utils.cache import WARNING_MESSAGES
import re
import logging

logger = logging.getLogger(__name__)

router = Router()

# Handler to send referral link when user presses "Invite Friends" button

WELCOME_BANNER_FILE_ID = None
@router.callback_query(F.data == "restart_registration")
@router.message(F.text == "🔄 Ro'yxatdan o'tishni qaytadan boshlash")
@router.message(F.text == "/restart")
async def restart_registration_handler(event: types.Message | types.CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    await state.clear()
    
    logger.info(f"User {user_id} requested registration restart")
    
    if isinstance(event, types.CallbackQuery):
        await event.answer("Ma'lumotlar tozalanmoqda...", show_alert=True)
        try: await event.message.delete()
        except: pass
        await start_registration(event.message, state)
    else:
        await event.answer("🔄 Ro'yxatdan o'tish jarayoni qaytadan boshlandi.", reply_markup=types.ReplyKeyboardRemove())
        await start_registration(event, state)

@router.message(CommandStart(), StateFilter("*"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Auto-delete tracked warnings in groups
    if user_id in WARNING_MESSAGES:
        warnings = WARNING_MESSAGES.pop(user_id, [])
        for chat_id, msg_id in warnings:
            try:
                await message.bot.delete_message(chat_id, msg_id)
            except:
                pass

    is_admin = user_id == ADMIN_ID
    
    # Check for referral link or deep link
    text = message.text or message.caption or ""
    args = text.split()
    referred_by = None
    order_deep_link = None
    
    if len(args) > 1:
        payload = args[1]
        if payload.startswith("ref_"):
            try: referred_by = int(payload.split("_")[1])
            except: pass
        elif payload.startswith("order_"):
            try: order_deep_link = payload.split("_")[1]
            except: pass
        elif payload == "restart":
            return await restart_registration_handler(message, state)

    # 0. Group Context Handling
    # We allow processing in groups, but avoid sending large menus there
    if message.chat.type in ["group", "supergroup"] and not message.text.startswith("/"):
        return

    await mark_user_started(user_id)
    user = await get_user(user_id)
    
    # Store referral if new user
    if referred_by and referred_by != user_id:
        await state.update_data(referred_by=referred_by)
    
    # Mandatory Subscription Check
    is_subscribed = await check_subscription(message.bot, user_id)
    if not is_subscribed:
        keyboard = await get_subscription_keyboard()
        await message.answer(
            "<b>ℹ️ BOTDAN FOYDALANISH UCHUN</b>\n\n"
            "Iltimos, botdan to'liq foydalanish va buyurtmalar berish uchun quyidagi kanallarga a'zo bo'ling:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    # Auto-detect language if not set
    detected_lang = 'uz'
    if message.from_user.language_code == 'ru':
        detected_lang = 'ru'
    
    is_fully_registered = False
    if user:
        # Deep Link Handling for Registered Users
        if order_deep_link and order_deep_link.isdigit():
            order = await get_order(int(order_deep_link))
            if not order:
                return await message.answer("❌ Buyurtma topilmadi yoki bekor qilingan.")
            
            # Check if they are an approved driver
            driver = await get_driver(user_id)
            if not driver or not driver[7]: # is_approved is at index 7
                return await message.answer("⚠️ Buyurtmani olish uchun avval haydovchi sifatida ro'yxatdan o'tishingiz va admin tomonidan tasdiqlanishingiz kerak.")
                
            # Show order details
            lang = user[8] or detected_lang
            # Let's just create a custom message for them
            text = f"📦 <b>Buyurtma #{order_deep_link}</b>\n\n"
            text += f"📍 {order[3]} ➔ {order[4]}\n"
            text += f"💰 Narxi: {order[5]:,} so'm\n"
            text += f"📅 Vaqt: {order[7] or 'Hozir'}"
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Buyurtmani qabul qilish", callback_data=f"accept_{order_deep_link}")],
                [InlineKeyboardButton(text="❌ Yopish", callback_data="close_wallet")]
            ])
            return await message.answer(text, reply_markup=kb, parse_mode="HTML")

        # Check if they have a role (they are already 'in the system')
        user_role = user[4]
        user_lang = user[8] or detected_lang
        
        # If they already chose a role, they shouldn't re-register
        if user_role:
            if order_deep_link == "new":
                from handlers.passenger import start_order
                await state.update_data(order_type='now')
                return await start_order(message, state)
            elif order_deep_link == "parcel_new":
                from handlers.parcel import start_parcel_order
                await state.update_data(order_type='parcel')
                return await start_parcel_order(message, state)
            # Fast track: show role selection even if registered, to allow easy switching/entry
            await send_role_selection(message, state, is_admin, user_lang)
            return

    # If we reach here, they are new or haven't chosen a role yet
    if message.from_user.is_bot:
        return # Safety check

    # Clear state for a fresh start BUT preserve referral if exists
    state_data = await state.get_data()
    ref_id = state_data.get('referred_by')
    
    await state.clear()
    
    if ref_id:
        await state.update_data(referred_by=ref_id)
    
    # We no longer delete the user record here to preserve 'bot starters' statistics
    # as per user request: "anyone who hits start is a user".

    # New User - Language Selection
    logger.info(f"Starting fresh registration for user {user_id} (Ref: {ref_id})")
    await start_registration(message, state)

async def start_registration(message: types.Message, state: FSMContext):
    user_id = message.chat.id # Use chat.id for direct messaging
    await state.clear()
    await state.set_state(Registration.choosing_lang)
    prompt = "🌍 Iltimos, tilni tanlang:\n🌍 Пожалуйста, выберите язык:\n🌍 Please choose your language:"
    try:
        await message.bot.send_message(user_id, prompt, reply_markup=get_language_keyboard())
    except Exception as e:
        logger.error(f"Failed to send language selection to {user_id}: {e}")
        # Fallback to answer if send_message fails
        await message.answer(prompt, reply_markup=get_language_keyboard())

@router.callback_query(Registration.choosing_lang, F.data.startswith("lang_"))
async def process_language_selection(callback: types.CallbackQuery, state: FSMContext):
    lang_code = callback.data.split("_")[1]
    await update_user_language(callback.from_user.id, lang_code)
    await state.update_data(lang=lang_code)
    try:
        await callback.message.delete()
    except:
        pass
    is_admin = callback.from_user.id == ADMIN_ID
    await send_role_selection(callback.message, state, is_admin, lang_code)
    await callback.answer()

async def send_role_selection(message: types.Message, state: FSMContext, is_admin: bool, lang: str):
    await state.set_state(Registration.choosing_role)
    
    role_prompt = get_trans(lang, 'role_selection_prompt_admin') if is_admin else get_trans(lang, 'role_selection_prompt_user')
    
    # Try to get dynamic welcome text via get_trans
    custom_caption = get_trans(lang, 'welcome_passenger')
    if custom_caption == TRANSLATIONS.get(lang, {}).get('welcome_passenger', ''):
        # If it's still default or not found, try the old bare key just in case
        bare_custom = await get_setting('welcome_text')
        if bare_custom:
            caption_text = bare_custom
        else:
            caption_text = get_trans(lang, 'welcome_caption_default')
    else:
        caption_text = custom_caption

    caption_text += f"\n\n{role_prompt}"
    
    custom_photo_id = await get_setting('welcome_photo')
    
    try:
        if custom_photo_id:
            await message.bot.send_photo(
                chat_id=message.chat.id,
                photo=custom_photo_id,
                caption=caption_text,
                reply_markup=get_role_keyboard(is_admin, lang=lang),
                parse_mode="HTML"
            )
        else:
            global WELCOME_BANNER_FILE_ID
            photo = WELCOME_BANNER_FILE_ID if WELCOME_BANNER_FILE_ID else FSInputFile("assets/banner.png")
            
            sent_msg = await message.bot.send_photo(
                chat_id=message.chat.id,
                photo=photo,
                caption=caption_text,
                reply_markup=get_role_keyboard(is_admin, lang=lang),
                parse_mode="HTML"
            )
            if not WELCOME_BANNER_FILE_ID and sent_msg.photo:
                WELCOME_BANNER_FILE_ID = sent_msg.photo[-1].file_id
    except:
        await message.bot.send_message(
            chat_id=message.chat.id,
            text=caption_text,
            reply_markup=get_role_keyboard(is_admin, lang=lang),
            parse_mode="HTML"
        )

async def send_welcome_message(message: types.Message, user, is_admin):
    role = user[4]
    user_id = user[0]
    lang = await get_user_language(user_id)
    
    # ADMIN is always shown the full menu first
    if is_admin:
        welcome_text = f"{get_trans(lang, 'admin_welcome')}\n\n{get_trans(lang, 'admin_panel_hint')}"
        await message.answer(
            welcome_text,
            reply_markup=await get_passenger_menu(is_admin=True, lang=lang),
            parse_mode="HTML"
        )
        return
    
    if role == 'passenger':
        from database.db import get_passenger_active_orders, get_passenger_pending_orders
        active = await get_passenger_active_orders(user_id)
        pending = await get_passenger_pending_orders(user_id)
        has_active = bool(active) or bool(pending)
        
        welcome_text = get_trans(lang, 'welcome_passenger').format(name=user[1] or message.from_user.full_name)
        await message.answer(welcome_text, reply_markup=await get_passenger_menu(is_admin, has_active_order=has_active, lang=lang), parse_mode="HTML")
    elif role == 'driver':
        from database.db import get_driver
        driver = await get_driver(user_id)
        if driver and driver[7]: # is_approved index is 7
            await message.answer(f"<b>👋 {get_trans(lang, 'role_driver')}!</b>\nOmon bo'ling.", reply_markup=await get_driver_menu(driver[6], is_admin, lang=lang), parse_mode="HTML")
        else:
            admin_url = await get_setting('admin_url', 'https://t.me/Admeral2002')
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_trans(lang, 'write_admin'), url=admin_url)],
                [InlineKeyboardButton(text=get_trans(lang, 'restart_registration_btn'), callback_data="restart_registration")]
            ])
            await message.answer(get_trans(lang, 'driver_pending'), reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_drv_"), F.from_user.id == ADMIN_ID)
async def admin_driver_approval(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    action = parts[2] # app / rej
    user_id = int(parts[3])
    
    user = await get_user(user_id)
    lang = user[8] if user else 'uz'
    
    if action == "app":
        from database.db import approve_driver
        await approve_driver(user_id)
        new_caption = callback.message.caption + "\n\n✅ <b>TASDIQLANDI</b>"
        await callback.message.edit_caption(caption=new_caption, parse_mode="HTML")
        try:
            # 1️⃣ Tasdiqlandi xabari + menyu
            await callback.bot.send_message(
                user_id,
                get_trans(lang, 'driver_approved'),
                reply_markup=await get_driver_menu(is_online=False, is_admin=(user_id == ADMIN_ID), lang=lang),
                parse_mode="HTML"
            )
            # 2️⃣ To'liq qo'llanma xabari
            guide = (
                "📘 <b>BOTDAN FOYDALANISH QO'LLANMASI</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"

                "🟢 <b>1. Onlayn bo'lish</b>\n"
                "Buyurtma olish uchun avval <b>\"🟢 Onlayn\"</b> tugmasini bosing.\n"
                "Oflayn bo'lsangiz — buyurtmalar kelmaydi.\n\n"

                "📥 <b>2. Buyurtma qabul qilish</b>\n"
                "Yangi buyurtma kelganda bot sizga xabar yuboradi:\n"
                "  • <b>✅ Qabul qilish</b> — buyurtmani olib, yo'lovchi bilan bog'lanasiz\n"
                "  • <b>💰 Narx taklif qilish</b> — o'z narxingizni yuboring\n"
                "  • <b>❌</b> — bu buyurtmani rad eting\n\n"

                "📍 <b>3. Yo'lovchiga yetib borganingizda</b>\n"
                "Buyurtmani qabul qilgach, <b>\"🚗 Yetib keldim\"</b> tugmasini bosing.\n"
                "Yo'lovchi xabar oladi.\n\n"

                "✅ <b>4. Safarni yakunlash</b>\n"
                "<b>\"✅ Yakunlash\"</b> tugmasini bosib safarni yoping.\n"
                "Yo'lovchi sizni baholaydi — yaxshi baho ko'proq buyurtma beradi!\n\n"

                "🛣 <b>5. Yo'nalish sozlamalari</b>\n"
                "Faqat ma'lum yo'nalishlarda ishlashni xohlasangiz:\n"
                "<b>Yo'nalish → Ish turi</b> menyusidan sozlang.\n\n"

                "💬 <b>6. Yo'lovchi bilan chat</b>\n"
                "Buyurtma qabul qilgach, to'g'ridan-to'g'ri bot orqali yo'lovchiga xabar yuborishingiz mumkin.\n\n"

                "📦 <b>7. Pochta buyurtmalari</b>\n"
                "<b>\"📦 Mavjud pochtalar\"</b> tugmasi orqali pochta buyurtmalarini ko'ring va qabul qiling.\n\n"

                "🏆 <b>8. Reyting va mukofotlar</b>\n"
                "Ko'proq safar = yuqori reyting = <b>prioritet buyurtmalar</b>!\n"
                "Haftalik liderlar jadvalida birinchi o'rinni egallang.\n\n"

                "💰 <b>9. Hamyon va to'lovlar</b>\n"
                "<b>\"💰 Hamyon\"</b> tugmasi orqali balansingizni ko'ring.\n"
                "Tarif sotib olish uchun admin bilan bog'laning.\n\n"

                "━━━━━━━━━━━━━━━━━━━━\n"
                "❓ Savollar bo'lsa: /start → Yordam bo'limiga murojaat qiling.\n"
                "🚀 <b>Omadli safarlar!</b>"
            )
            await callback.bot.send_message(user_id, guide, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Could not notify user {user_id} of approval: {e}")
        await callback.answer("✅ Haydovchi tasdiqlandi!")
    else:
        await delete_user(user_id)
        new_caption = callback.message.caption + f"\n\n❌ <b>RAD ETILDI</b>"
        await callback.message.edit_caption(caption=new_caption, parse_mode="HTML")
        try:
            await callback.bot.send_message(user_id, get_trans(lang, 'registration_rejected_msg'), parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Could not notify user {user_id} of rejection: {e}")
        await callback.answer("❌ Haydovchi rad etildi!")

@router.message(Registration.choosing_role, F.text == "🛠 Admin Panel", F.from_user.id == ADMIN_ID)
async def process_admin_panel_entry(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.admin import get_admin_main_kb
    from database.db import get_admin
    adm = await get_admin(message.from_user.id)
    perms = adm[2] if adm else 'all'
    await message.answer("<b>🛠 ADMIN PANEL</b>", reply_markup=get_admin_main_kb(message.from_user.id, perms), parse_mode="HTML")

@router.message(Registration.entering_name, F.text, ~F.text.startswith("/"))
async def process_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    words = [w.capitalize() for w in full_name.split()]
    full_name = " ".join(words)
    
    data = await state.get_data()
    lang = data.get('lang', 'uz')

    # 1. Supported characters: Latin and Cyrillic + allowed symbols
    is_alpha = bool(re.match(r"^[A-Za-zА-Яа-яЁё'ʻʼ\s\-]+$", full_name))
    if not is_alpha:
        msg = "⚠️ <b>Xatolik:</b> Ismingizda faqat harflar bo'lishi kerak!" if lang == 'uz' else "⚠️ <b>Ошибка:</b> Имя должно содержать только буквы!"
        return await message.answer(msg, parse_mode="HTML")

    # 2. Basic format: 1-4 words
    if not (1 <= len(words) <= 4):
        msg = "⚠️ <b>Xatolik:</b> Ismingizni to'liqroq kiriting (Masalan: Aliyev Ali)!" if lang == 'uz' else "⚠️ <b>Ошибка:</b> Введите полное имя (например: Алиев Али)!"
        return await message.answer(msg, parse_mode="HTML")

    # 3. Minimum length
    if len(full_name) < 5:
        msg = "⚠️ <b>Xatolik:</b> Ismingiz juda qisqa!" if lang == 'uz' else "⚠️ <b>Ошибка:</b> Имя слишком короткое!"
        return await message.answer(msg, parse_mode="HTML")
    
    # 4. Repeating characters
    if any(re.search(r'(.)\1\1', w.lower()) for w in words):
        msg = "⚠️ <b>Xatolik:</b> Ismda ketma-ket takrorlangan harflar mavjud!" if lang == 'uz' else "⚠️ <b>Ошибка:</b> В имени есть повторяющиеся буквы!"
        return await message.answer(msg, parse_mode="HTML")

    # 5. Vowels check (Both Latin and Cyrillic)
    vowels = r'[aeiouyʻаеёиоуыэюя]'
    if not all(re.search(vowels, w.lower()) for w in words):
        msg = "⚠️ <b>Xatolik:</b> Ismda unli harflar bo'lishi shart!" if lang == 'uz' else "⚠️ <b>Ошибка:</b> В имени должны быть гласные буквы!"
        return await message.answer(msg, parse_mode="HTML")
        
    await state.update_data(full_name=full_name)
    await state.set_state(Registration.sending_phone)
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    
    # Correct key: send_phone
    await message.answer(get_trans(lang, 'send_phone'), reply_markup=get_phone_keyboard(lang=lang), parse_mode="HTML")

@router.message(Registration.entering_name)
async def process_name_invalid(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    await message.answer(get_trans(lang, 'invalid_fullname'), parse_mode="HTML")

@router.message(Registration.choosing_role, IsMenuButton('role_passenger'))
async def process_role_passenger(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    # If already registered, fast-track to menu
    if user and user[4]:
        from database.db import get_passenger_active_orders, get_passenger_pending_orders
        active = await get_passenger_active_orders(user_id)
        pending = await get_passenger_pending_orders(user_id)
        has_active = bool(active) or bool(pending)
        
        lang = user[8] or 'uz'
        is_admin = user_id == ADMIN_ID
        welcome_text = get_trans(lang, 'welcome_passenger').format(name=user[1] or message.from_user.full_name)
        
        await state.clear()
        return await message.answer(welcome_text, reply_markup=await get_passenger_menu(is_admin, has_active_order=has_active, lang=lang), parse_mode="HTML")

    await state.update_data(role='passenger')
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    await state.set_state(Registration.entering_name)
    await message.answer(get_trans(lang, 'enter_fullname'), reply_markup=types.ReplyKeyboardRemove(), parse_mode="HTML")

@router.message(Registration.choosing_role, IsMenuButton('role_driver'))
async def process_role_driver(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    # If already an approved driver, fast-track to menu
    if user and user[4] == 'driver':
        driver = await get_driver(user_id)
        if driver and driver[7]: # is_approved
            lang = user[8] or 'uz'
            is_admin = user_id == ADMIN_ID
            await state.clear()
            return await message.answer(f"<b>👋 {get_trans(lang, 'role_driver')}!</b>\nXush kelibsiz.", reply_markup=await get_driver_menu(driver[6], is_admin, lang=lang), parse_mode="HTML")

    await state.update_data(role='driver')
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    await state.set_state(Registration.entering_name)
    await message.answer(get_trans(lang, 'driver_reg_info'), reply_markup=types.ReplyKeyboardRemove(), parse_mode="HTML")

@router.message(Registration.sending_phone, F.contact)
@router.message(Registration.sending_phone, F.text, ~F.text.startswith("/"))
async def process_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    
    phone_raw = message.contact.phone_number if message.contact else message.text
    if not phone_raw: return
    
    phone = normalize_phone(phone_raw)
    if not is_uzbek_number(phone):
        return await message.answer(get_trans(lang, 'invalid_phone'), parse_mode="HTML")
        
    await state.update_data(phone=phone)
    await state.set_state(Registration.entering_secondary_phone)
    await message.answer(get_trans(lang, 'enter_secondary_phone'), reply_markup=get_secondary_phone_keyboard(lang=lang), parse_mode="HTML")

@router.message(Registration.sending_phone)
async def process_phone_invalid(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    await message.answer(get_trans(lang, 'invalid_phone'), parse_mode="HTML")

@router.message(Registration.entering_secondary_phone, F.text, ~F.text.startswith("/"))
async def process_secondary_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    
    if message.text == get_trans(lang, 'skip'):
        await state.update_data(secondary_phone=None)
        return await finalize_registration_choice(message, state)
        
    phone = normalize_phone(message.text)
    if not is_uzbek_number(phone):
        return await message.answer(get_trans(lang, 'invalid_phone'), reply_markup=get_secondary_phone_keyboard(lang), parse_mode="HTML")
        
    await state.update_data(secondary_phone=phone)
    await finalize_registration_choice(message, state)

async def finalize_registration_choice(event: types.Message | types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    role = data.get('role')
    
    if role == 'driver':
        await state.set_state(Registration.entering_car_name)
        await event.bot.send_message(event.from_user.id, get_trans(lang, 'enter_car_name'), reply_markup=types.ReplyKeyboardRemove(), parse_mode="HTML")
    else:
        await finalize_registration(event, state)

@router.message(Registration.entering_car_name, F.text, ~F.text.startswith("/"))
async def process_car_name(message: types.Message, state: FSMContext):
    car_name = message.text.strip()
    if len(car_name) < 5:
        return await message.answer("⚠️ <b>Mashina modelini to'liqroq yozing!</b>\nMasalan: <i>Chevrolet Cobalt</i>", parse_mode="HTML")
        
    await state.update_data(car_name=car_name)
    await state.set_state(Registration.entering_car_number)
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    await message.answer(get_trans(lang, 'enter_car_number'), parse_mode="HTML")

@router.message(Registration.entering_car_number, F.text, ~F.text.startswith("/"))
async def process_car_number(message: types.Message, state: FSMContext):
    plate = normalize_plate(message.text)
    if not validate_uzb_plate(plate):
        return await message.answer("⚠️ <b>Davlat raqami xato!</b>\nMasalan: <code>70A123BC</code>", parse_mode="HTML")
        
    await state.update_data(car_number=plate)
    await state.set_state(Registration.entering_car_photo)
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    
    example_photo = FSInputFile("assets/car_example.png")
    await message.answer_photo(
        photo=example_photo,
        caption=get_trans(lang, 'send_car_photo'),
        parse_mode="HTML"
    )


async def finalize_registration(event: types.Message | types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = event.from_user.id
    
    # Save to DB
    is_new = await add_user(
        user_id=user_id,
        full_name=data.get('full_name'),
        phone=data.get('phone'),
        role=data.get('role'),
        referred_by=data.get('referred_by'),
        secondary_phone=data.get('secondary_phone')
    )
    
    referrer_id = data.get('referred_by')
    if is_new and referrer_id and referrer_id != user_id:
        bonus_amount = float(await get_setting('ref_bonus', '500'))
        
        if bonus_amount > 0:
            try:
                await update_user_balance(referrer_id, bonus_amount, f"🎁 Taklif qilingan do'st uchun bonus", 'in')
                ref_lang = await get_user_language(referrer_id)
                msg_uz = f"🎉 <b>Tabriklaymiz!</b>\n\nSizning havolangiz orqali yangi foydalanuvchi ro'yxatdan o'tdi!\nSizning hisobingizga <b>{bonus_amount:,.0f} so'm</b> bonus qo'shildi."
                msg_ru = f"🎉 <b>Поздравляем!</b>\n\nПо вашей ссылке зарегистрировался новый пользователь!\nНа ваш счет начислен бонус в размере <b>{bonus_amount:,.0f} сум</b>."
                
                await event.bot.send_message(
                    referrer_id,
                    msg_uz if ref_lang == 'uz' else msg_ru,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to give referral bonus to {referrer_id}: {e}")
    
    if data.get('role') == 'driver':
        # Add driver details
        await add_driver_details(
            user_id=user_id,
            car_name=data.get('car_name'),
            car_number=data.get('car_number'),
            car_photo=data.get('car_photo'),
            is_approved=0
        )
        lang = data.get('lang', 'uz')
        
        # Notify Admin
        admin_text = (
            f"<b>🆕 YANGI HAYDOVCHI!</b> {'⚠️ <b>(OCR BYPASS)</b>' if data.get('ocr_bypassed') else ''}\n"
            "━━━━━━━━━━━━━━\n"
            f"👤 Ism: {data.get('full_name')}\n"
            f"📞 Tel: {data.get('phone')}\n"
            f"🚗 Mashina: {data.get('car_name')}\n"
            f"🔢 Raqam: {data.get('car_number')}\n"
            f"🆔 ID: <code>{user_id}</code>"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm_drv_app_{user_id}"),
             InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_drv_rej_{user_id}")]
        ])
        
        try:
            await event.bot.send_photo(ADMIN_ID, data.get('car_photo'), caption=admin_text, reply_markup=kb, parse_mode="HTML")
        except:
            await event.bot.send_message(ADMIN_ID, admin_text, reply_markup=kb, parse_mode="HTML")

        # User side
        admin_url = await get_setting('admin_url', 'https://t.me/Admeral2002')
        kb_user = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👨‍💻 Admin bilan bog'lanish", url=admin_url)],
            [InlineKeyboardButton(text="🔄 Ma'lumotlarni qayta kiritish", callback_data="restart_registration")]
        ])
        await event.bot.send_message(user_id, get_trans(lang, 'driver_pending'), reply_markup=kb_user, parse_mode="HTML")
    else:
        # Passenger setup
        lang = data.get('lang', 'uz')
        await event.bot.send_message(user_id, get_trans(lang, 'reg_success'), reply_markup=await get_passenger_menu(user_id==ADMIN_ID, lang=lang), parse_mode="HTML")
        
    await state.clear()


@router.message(Registration.entering_car_photo, F.photo)
async def process_car_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    
    photo = message.photo[-1]
    await state.update_data(last_photo_id=photo.file_id) # Store for potential bypass
    
    # Check if OCR is globally enabled
    ocr_enabled = await get_setting('ocr_enabled', '1')
    if ocr_enabled == '0':
        # Skip OCR entirely for maximum speed!
        await state.update_data(car_photo=photo.file_id)
        await finalize_registration(message, state)
        return
        
    waiting_msg = await message.answer(get_trans(lang, 'ocr_checking'), parse_mode="HTML")
    
    try:
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        photo_stream = await message.bot.download_file(file.file_path)
        photo_data = photo_stream.read()
        if reader is None:
            await waiting_msg.delete()
            return await message.answer("⚠️ OCR tizimi hozircha ishlamayapti. Iltimos, adminga murojaat qiling.")

        entered_plate = data.get('car_number')
        detected_plate = await extract_plate_number(photo_data, entered_plate)

        if not detected_plate:
            await waiting_msg.delete()
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🙋‍♂️ Baribir yuborish (Admin tekshiradi)", callback_data="bypass_ocr_photo")]
            ])
            return await message.answer(
                get_trans(lang, 'ocr_fail') + "\n\n<i>Yoki rasmda raqam aniq ko'ringan bo'lsa, 'Baribir yuborish' tugmasini bosing:</i>", 
                reply_markup=kb, parse_mode="HTML"
            )

        if normalize_for_comparison(detected_plate) != normalize_for_comparison(entered_plate):
            await waiting_msg.delete()
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🙋‍♂️ Baribir yuborish (Admin tekshiradi)", callback_data="bypass_ocr_photo")]
            ])
            return await message.answer(
                get_trans(lang, 'ocr_mismatch').format(entered_plate=entered_plate, detected_plate=detected_plate) + 
                "\n\n<i>Yoki rasmda raqam to'g'ri bo'lsa, 'Baribir yuborish' tugmasini bosing:</i>",
                reply_markup=kb, parse_mode="HTML"
            )

        # Success: OCR matched
        await state.update_data(car_photo=photo.file_id)
        await finalize_registration(message, state)
        await waiting_msg.delete()
        
        # Admin log
        admin_text = f"<b>✅ OCR TASDIQLANDI</b>\n\n👤 {data.get('full_name')}\n🚗 {data.get('car_name')}\n🔢 {entered_plate}"
        try:
            await message.bot.send_photo(ADMIN_ID, photo.file_id, caption=admin_text, parse_mode="HTML")
        except:
            pass
            
    except Exception as e:
        logger.error(f"OCR Error in registration: {e}")
        try: await waiting_msg.delete()
        except: pass
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🙋‍♂️ Baribir yuborish (Admin tekshiradi)", callback_data="bypass_ocr_photo")]
        ])
        await message.answer(
            "❌ <b>Tahlil qilishda xatolik yuz berdi.</b>\n\nIltimos qaytadan urinib ko'ring yoki 'Baribir yuborish' tugmasini bosing (Admin qo'lda tekshiradi).",
            reply_markup=kb, parse_mode="HTML"
        )

@router.callback_query(F.data == "bypass_ocr_photo")
async def bypass_ocr_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    
    photo_id = data.get('last_photo_id')
    if not photo_id:
        return await callback.answer("❌ Xatolik: Rasm topilmadi. Iltimos qaytadan yuboring.", show_alert=True)
        
    await callback.answer("✅ Admin tekshiruvi uchun yuborildi.")
    await state.update_data(car_photo=photo_id, ocr_bypassed=True)
    
    try: await callback.message.delete()
    except: pass
    
    await finalize_registration(callback, state)

@router.message(Registration.entering_car_photo)
async def process_car_photo_invalid(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('lang', 'uz')
    await message.answer(get_trans(lang, 'send_car_photo'), parse_mode="HTML")

@router.callback_query(F.data == "check_sub_again")
async def check_sub_again(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    is_subscribed = await check_subscription(callback.bot, user_id, bypass_cache=True)
    lang = await get_user_language(user_id)

    if is_subscribed:
        msg = (
            "✅ Tabriklaymiz! Siz barcha kanallarga muvaffaqiyatli obuna bo'ldingiz."
            if lang == 'uz' else
            "✅ Поздравляем! Вы успешно подписались на все каналы."
        )
        await callback.answer(msg, show_alert=True)
        try:
            try:
                await callback.message.delete()
            except:
                pass
        except Exception:
            pass

        # ❌ callback.message.from_user = callback.from_user  ← Pydantic frozen xatosi
        # ✅ To'g'ridan-to'g'ri kerakli flow ni chaqiramiz
        await mark_user_started(user_id)
        user = await get_user(user_id)
        is_admin = user_id == ADMIN_ID

        if user and user[4]:  # Rol tanlangan — xush kelibsiz sahifasi
            await send_welcome_message(callback.message, user, is_admin)
        else:  # Yangi foydalanuvchi — ro'yxatdan o'tish
            await start_registration(callback.message, state)
    else:
        msg = (
            "❌ Kechirasiz, siz hali barcha kanallarga obuna bo'lmagansiz. Iltimos, qaytadan tekshiring."
            if lang == 'uz' else
            "❌ Извините, вы еще не подписались на все каналы. Пожалуйста, проверьте еще раз."
        )
        await callback.answer(msg, show_alert=True)



