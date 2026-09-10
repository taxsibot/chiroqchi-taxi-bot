from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from database.db import get_user, update_user_profile, get_driver, add_driver_details, update_user_language, get_user_stats_rich, calculate_loyalty_level
from utils.states import ProfileStates
from utils.phone_validation import is_uzbek_number, normalize_phone
from utils.ocr_helper import validate_uzb_plate, normalize_plate, extract_plate_number
from keyboards.reply import get_passenger_menu, get_driver_menu, get_phone_keyboard
from keyboards.inline import get_profile_inline_keyboard, get_edit_cancel_keyboard
from utils.locales import get_trans
from utils.utils import IsMenuButton
from config import ADMIN_ID

router = Router()

@router.message(IsMenuButton('profile'))
async def show_profile(message: types.Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if not user:
        return # User should be registered
    
    # user structure: user_id(0), full_name(1), phone(2), secondary(3), role(4), status(5), balance(6), ref_by(7), lang(8), bonus_date(9), reg_date(10), cashback(11)
    user_id, full_name, phone, secondary, role, status, balance, ref_by, lang = user[:9]
    cashback_bal = user[11] if len(user) > 11 else 0
    
    stats = await get_user_stats_rich(message.from_user.id)
    level_key = calculate_loyalty_level(stats['trips'])
    level_text = get_trans(lang, level_key)
    
    role_text = get_trans(lang, 'role_passenger') if role == 'passenger' else get_trans(lang, 'role_driver')
    status_text = get_trans(lang, 'profile_status_active') if status == 'active' else get_trans(lang, 'profile_status_blocked')

    import html
    safe_name = html.escape(full_name)
    
    text = get_trans(lang, 'profile_level_title').format(level=level_text) + "\n"
    text += "━━━━━━━━━━━━━━\n\n"
    text += get_trans(lang, 'profile_id').format(user_id=user_id) + "\n"
    text += get_trans(lang, 'profile_name').format(full_name=safe_name) + "\n"
    text += get_trans(lang, 'profile_phone').format(phone=phone) + "\n"
    text += get_trans(lang, 'profile_balance').format(balance=balance) + "\n"
    text += f"💎 Keshbek: <b>{cashback_bal:,} so'm</b>\n"
    text += get_trans(lang, 'profile_role').format(role=role_text) + "\n"
    text += get_trans(lang, 'profile_trips').format(trips=stats['trips']) + "\n"
    text += get_trans(lang, 'profile_referrals').format(count=stats['referrals']) + "\n"
    text += f"{get_trans(lang, 'profile_status')} <b>{status_text}</b>\n"
    
    if role == 'driver':
        driver = await get_driver(user_id)
        if driver:
            # Structure: user_id(0), car_name(1), car_number(2), car_class(3), rating(4), total_rides(5), is_online(6), is_approved(7)
            is_approved = driver[7] == 1
            approved_text = get_trans(lang, 'doc_status_approved') if is_approved else get_trans(lang, 'doc_status_pending')
            
            safe_car_name = html.escape(driver[1])
            text += get_trans(lang, 'profile_car_header') + "\n"
            text += "━━━━━━━━━━━━━━\n"
            text += get_trans(lang, 'profile_car_model').format(model=safe_car_name) + "\n"
            text += get_trans(lang, 'profile_car_plate').format(plate=driver[2]) + "\n"
            text += get_trans(lang, 'profile_class').format(car_class=driver[3]) + "\n"
            text += get_trans(lang, 'profile_rating').format(rating=round(driver[4], 1)) + "\n"
            text += f"{get_trans(lang, 'profile_docs')}{approved_text}\n"

    await message.answer(text, reply_markup=get_profile_inline_keyboard(role, lang), parse_mode="HTML")

@router.callback_query(F.data == "close_profile")
async def close_profile(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass
    await callback.answer()

@router.callback_query(F.data == "edit_name")
async def edit_name_start(callback: types.CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    lang = user[8]
    await state.set_state(ProfileStates.editing_name)
    await callback.message.answer(get_trans(lang, 'enter_fullname'), reply_markup=get_edit_cancel_keyboard(lang), parse_mode="HTML")
    await callback.answer()

@router.message(ProfileStates.editing_name, F.text, ~F.text.startswith("/"))
async def process_edit_name(message: types.Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user[8]
    
    text = message.text or message.caption or ""
    if len(text.split()) < 2:
        await message.answer(get_trans(lang, 'invalid_fullname'), parse_mode="HTML")
        return
    
    await update_user_profile(message.from_user.id, full_name=text)
    await state.clear()
    await message.answer(get_trans(lang, 'edit_success'), reply_markup=await get_passenger_menu(is_admin=message.from_user.id==ADMIN_ID, lang=lang))
    await show_profile(message, state)

@router.callback_query(F.data == "edit_language")
async def edit_language_start(callback: types.CallbackQuery):
    from keyboards.reply import get_language_keyboard
    user = await get_user(callback.from_user.id)
    lang = user[8]
    
    # Prefix callback data to handle specifically in profile
    kb = get_language_keyboard()
    new_kb = []
    for row in kb.inline_keyboard:
        new_row = []
        for btn in row:
            l_code = btn.callback_data.split("_")[1]
            new_row.append(types.InlineKeyboardButton(text=btn.text, callback_data=f"pro_lang_{l_code}"))
        new_kb.append(new_row)
        
    await callback.message.answer(get_trans(lang, 'choose_lang'), reply_markup=types.InlineKeyboardMarkup(inline_keyboard=new_kb))
    await callback.answer()

@router.callback_query(F.data.startswith("pro_lang_"))
async def process_profile_lang(callback: types.CallbackQuery, state: FSMContext):
    lang_code = callback.data.split("_")[2]
    await update_user_language(callback.from_user.id, lang_code)
    
    user = await get_user(callback.from_user.id)
    is_admin = callback.from_user.id == ADMIN_ID
    
    if user[4] == 'passenger':
        menu = await get_passenger_menu(is_admin, lang=lang_code)
    else:
        dr = await get_driver(callback.from_user.id)
        menu = await get_driver_menu(bool(dr[6]) if dr else False, is_admin, lang=lang_code)
    
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer(get_trans(lang_code, 'lang_changed'), reply_markup=menu)

@router.callback_query(F.data == "cancel_edit")
async def cancel_edit(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass
    await callback.answer()

@router.callback_query(F.data == "edit_phone")
async def edit_phone_start(callback: types.CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    lang = user[8]
    await state.set_state(ProfileStates.editing_phone)
    await callback.message.answer(get_trans(lang, 'send_phone'), reply_markup=get_phone_keyboard(lang), parse_mode="HTML")
    await callback.answer()

@router.message(ProfileStates.editing_phone, F.contact | F.text)
async def process_edit_phone(message: types.Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user[8]
    phone_raw = message.contact.phone_number if message.contact else (message.text or message.caption)
    
    if not phone_raw or not is_uzbek_number(phone_raw):
        await message.answer(get_trans(lang, 'invalid_phone'), parse_mode="HTML")
        return
        
    phone = normalize_phone(phone_raw)
    await update_user_profile(message.from_user.id, phone=phone)
    await state.clear()
    await message.answer(get_trans(lang, 'edit_success'), reply_markup=await get_passenger_menu(is_admin=message.from_user.id==ADMIN_ID, lang=lang))
    await show_profile(message, state)

@router.callback_query(F.data == "edit_car")
async def edit_car_start(callback: types.CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    lang = user[8]
    if user[4] != 'driver':
        return await callback.answer("Faqat haydovchilar uchun!", show_alert=True)
    
    await state.set_state(ProfileStates.editing_car_name)
    await callback.message.answer(get_trans(lang, 'enter_car_name'), reply_markup=get_edit_cancel_keyboard(lang), parse_mode="HTML")
    await callback.answer()

@router.message(ProfileStates.editing_car_name, F.text, ~F.text.startswith("/"))
async def process_edit_car_name(message: types.Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user[8]
    await state.update_data(new_car_name=message.text)
    await state.set_state(ProfileStates.editing_car_number)
    await message.answer(get_trans(lang, 'enter_car_number'), reply_markup=get_edit_cancel_keyboard(lang), parse_mode="HTML")

@router.message(ProfileStates.editing_car_number, F.text, ~F.text.startswith("/"))
async def process_edit_car_number(message: types.Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    lang = user[8]
    if not validate_uzb_plate(message.text):
        await message.answer(get_trans(lang, 'enter_car_number'), parse_mode="HTML")
        return
    
    plate = normalize_plate(message.text)
    await add_driver_details(message.from_user.id, (await state.get_data())['new_car_name'], plate, is_approved=0)
    await state.clear()
    await message.answer(get_trans(lang, 'car_update_pending'), reply_markup=await get_driver_menu(is_online=False, is_admin=message.from_user.id==ADMIN_ID, lang=lang))
    await show_profile(message, state)
