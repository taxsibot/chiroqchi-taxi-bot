from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from database.db import (
    create_order, get_user_language, get_setting, get_online_driver_ids,
    save_user_address, get_saved_addresses
)
from utils.states import ParcelProcess
from keyboards.reply import get_passenger_menu
from utils.order_helpers import wait_for_drivers_task
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from utils.locales import get_trans
from utils.utils import IsMenuButton
import asyncio
import re

router = Router()

from utils.route_helper import get_location_keyboard

@router.message(F.chat.type == "private", IsMenuButton('order_parcel'))
async def start_parcel_order(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    kb_reply = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=get_trans(lang, 'back'))]
    ], resize_keyboard=True)
    
    online_drivers = await get_online_driver_ids()
    online_count = len(online_drivers)
    
    msg_text = f"<b>{get_trans(lang, 'order_parcel')}</b>"
    if online_count > 0:
        msg_text += "\n\n" + get_trans(lang, 'online_drivers_count').format(count=online_count)
    else:
        msg_text += "\n\n" + get_trans(lang, 'no_online_drivers')
        
    await state.update_data(order_type='now', scheduled_time=None)
    await state.set_state(ParcelProcess.entering_from)
    
    await message.answer(msg_text, reply_markup=kb_reply, parse_mode="HTML")
    
    q_text = get_trans(lang, 'where_from')
    kb = await get_location_keyboard("from", message.from_user.id, lang=lang, prefix="p_loc_")
    await message.answer(f"<b>{q_text}</b>\n{get_trans(lang, 'choose_from_list')}", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("p_loc_from_"))
async def pick_from_location(callback: types.CallbackQuery, state: FSMContext):
    place = callback.data.replace("p_loc_from_", "")
    lang = await get_user_language(callback.from_user.id)
    if place == "custom":
        q_text = get_trans(lang, 'where_from')
        try:
            await callback.message.edit_text(f"✏️ <b>{q_text.replace('🔴 ', '')}</b>\n<i>Manzilni o'zingiz yozing:</i>", parse_mode="HTML")
        except:
            pass
        await state.set_state(ParcelProcess.entering_from)
        await callback.answer()
        return
    if place == "none" or place == "back":
        await callback.answer()
        return
    await state.update_data(from_loc=place)
    await save_user_address(callback.from_user.id, place)
    await state.set_state(ParcelProcess.entering_to)
    q_text = get_trans(lang, 'where_to')
    kb = await get_location_keyboard("to", callback.from_user.id, lang=lang, prefix="p_loc_")
    try:
        await callback.message.edit_text(f"🔴 Qayerdan: <b>{place}</b>\n\n<b>{q_text}</b>\n{get_trans(lang, 'choose_from_list')}", reply_markup=kb, parse_mode="HTML")
    except:
        pass
    await callback.answer()

@router.callback_query(F.data.startswith("p_loc_to_"))
async def pick_to_location(callback: types.CallbackQuery, state: FSMContext):
    place = callback.data.replace("p_loc_to_", "")
    lang = await get_user_language(callback.from_user.id)
    if place == "custom":
        q_text = get_trans(lang, 'where_to')
        try:
            await callback.message.edit_text(f"✏️ <b>{q_text.replace('🏁 ', '')}</b>\n<i>Manzilni o'zingiz yozing:</i>", parse_mode="HTML")
        except:
            pass
        await state.set_state(ParcelProcess.entering_to)
        await callback.answer()
        return
    if place == "none":
        await callback.answer()
        return
    
    data = await state.get_data()
    from_loc = data.get('from_loc', '-')
    
    await state.update_data(to_loc=place)
    await save_user_address(callback.from_user.id, place)
    await state.set_state(ParcelProcess.entering_price)
    try:
        await callback.message.edit_text(f"🔴 Qayerdan: <b>{from_loc}</b>\n🏁 Qayerga: <b>{place}</b>", parse_mode="HTML")
    except:
        pass
    await callback.message.answer(f"<b>{get_trans(lang, 'parcel_price_q')}</b>", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
    await callback.answer()

@router.message(ParcelProcess.entering_from, F.text)
async def process_from(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    if message.text == get_trans(lang, 'back'):
        await state.clear()
        return await message.answer(get_trans(lang, 'cancel'), reply_markup=await get_passenger_menu(lang=lang))
        
    await state.update_data(from_loc=message.text)
    await save_user_address(message.from_user.id, message.text)
    await state.set_state(ParcelProcess.entering_to)
    q_text = f"<b>{get_trans(lang, 'parcel_to_q')}</b>"
    kb = await _get_location_keyboard("to", message.from_user.id, lang=lang)
    await message.answer(f"{q_text}\n<i>Quyidagi ro'yxatdan tanlang:</i>", reply_markup=kb, parse_mode="HTML")

@router.message(ParcelProcess.entering_to, F.text)
async def process_to(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    if message.text == get_trans(lang, 'back'): return await start_parcel_order(message, state)
    await state.update_data(to_loc=message.text)
    await save_user_address(message.from_user.id, message.text)
    await state.set_state(ParcelProcess.entering_price)
    
    kb_reply = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=get_trans(lang, 'back'))]
    ], resize_keyboard=True)
    await message.answer(f"<b>{get_trans(lang, 'parcel_price_q')}</b>", reply_markup=kb_reply, parse_mode="HTML")

@router.message(ParcelProcess.entering_price, F.text)
async def process_price(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    if message.text == get_trans(lang, 'back'):
        await state.set_state(ParcelProcess.entering_to)
        q_text = f"<b>{get_trans(lang, 'parcel_to_q')}</b>"
        kb = await _get_location_keyboard("to", message.from_user.id, lang=lang)
        kb_reply = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=get_trans(lang, 'back'))]], resize_keyboard=True)
        return await message.answer(f"{q_text}\n<i>Quyidagi ro'yxatdan tanlang:</i>", reply_markup=kb, parse_mode="HTML")

    try:
        price_str = message.text.replace(" ", "").replace(",", "").replace(".", "")
        if not price_str.isdigit():
            return await message.answer("❌ Iltimos, faqat raqam kiriting!")
            
        price = float(price_str)
        min_price = float(await get_setting('min_price', '5000'))
        
        if price < min_price:
            return await message.answer(f"❌ Minimal narx: {int(min_price):,} so'm")

        surge_mult = await get_setting('surge_multiplier', '1.0')
        final_price = int(price * float(surge_mult))
        await state.update_data(price=final_price)
        await state.set_state(ParcelProcess.waiting_for_parcel_type)
        kb_reply = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=get_trans(lang, 'back'))]], resize_keyboard=True)
        await message.answer(f"<b>{get_trans(lang, 'parcel_type_q')}</b>", reply_markup=kb_reply, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

@router.message(ParcelProcess.entering_price)
async def process_price_invalid(message: types.Message, state: FSMContext):
    await message.answer("❌ Iltimos, narxni faqat raqamlarda kiriting!")

@router.message(ParcelProcess.waiting_for_parcel_type, F.text)
async def process_parcel_type(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    if message.text == get_trans(lang, 'back'):
        await state.set_state(ParcelProcess.entering_price)
        kb_reply = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=get_trans(lang, 'back'))]], resize_keyboard=True)
        return await message.answer(f"<b>{get_trans(lang, 'parcel_price_q')}</b>", reply_markup=kb_reply, parse_mode="HTML")

    text = message.text.strip()
    
    if len(text) < 3:
        return await message.answer("❌ Pochta turi/nomi juda qisqa (kamida 3 ta belgi).")
        
    if len(set(text.lower().replace(" ", ""))) < 2:
        return await message.answer("❌ Iltimos, pochta turi haqida aniqroq ma'lumot yozing.")

    await state.update_data(parcel_type=text)
    await state.set_state(ParcelProcess.waiting_for_parcel_receiver)
    kb_reply = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=get_trans(lang, 'back'))]], resize_keyboard=True)
    await message.answer(f"<b>{get_trans(lang, 'parcel_receiver_q')}</b>", reply_markup=kb_reply, parse_mode="HTML")

@router.message(ParcelProcess.waiting_for_parcel_receiver, F.text)
async def process_parcel_receiver(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    if message.text == get_trans(lang, 'back'):
        await state.set_state(ParcelProcess.waiting_for_parcel_type)
        kb_reply = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=get_trans(lang, 'back'))]], resize_keyboard=True)
        return await message.answer(f"<b>{get_trans(lang, 'parcel_type_q')}</b>", reply_markup=kb_reply, parse_mode="HTML")

    from utils.phone_validation import is_uzbek_number, normalize_phone
    
    if not is_uzbek_number(message.text):
        return await message.answer(get_trans(lang, 'invalid_phone'))
        
    phone = normalize_phone(message.text)
    await state.update_data(parcel_receiver=phone)
    await state.set_state(ParcelProcess.waiting_for_parcel_photo)
    kb_reply = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=get_trans(lang, 'back'))]], resize_keyboard=True)
    await message.answer(get_trans(lang, 'send_parcel_photo'), reply_markup=kb_reply, parse_mode="HTML")

@router.message(ParcelProcess.waiting_for_parcel_photo, F.photo)
async def process_parcel_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await finalize_parcel_creation(message, state, photo_id)

@router.message(ParcelProcess.waiting_for_parcel_photo)
async def process_parcel_photo_invalid(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    if getattr(message, 'text', '') == get_trans(lang, 'back'):
        await state.set_state(ParcelProcess.waiting_for_parcel_receiver)
        kb_reply = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=get_trans(lang, 'back'))]], resize_keyboard=True)
        return await message.answer(f"<b>{get_trans(lang, 'parcel_receiver_q')}</b>", reply_markup=kb_reply, parse_mode="HTML")

    await message.answer(get_trans(lang, 'send_parcel_photo'), parse_mode="HTML")

# Skip callback removed as photo is mandatory

async def finalize_parcel_creation(message: types.Message, state: FSMContext, photo_id: str = None):
    data = await state.get_data()
    lang = await get_user_language(message.from_user.id)
    
    from_loc = data.get('from_loc', '-')
    to_loc = data.get('to_loc', '-')
    p_type = data.get('parcel_type', '-')
    p_rec = data.get('parcel_receiver', '-')
    
    import html
    safe_to = html.escape(to_loc)
    safe_type = html.escape(p_type)
    safe_rec = html.escape(p_rec)
    
    full_to_loc = f"{safe_to}\n📦 <b>Turi:</b> {safe_type}\n📞 <b>Tel:</b> {safe_rec}"

    price = data.get('price')
    if not price:
        return await message.answer("⚠️ Ma'lumotlar yo'qoldi. Iltimos, qaytadan boshlang.")

    order_id = await create_order(
        passenger_id=message.from_user.id, 
        from_loc=from_loc, 
        to_loc=full_to_loc, 
        price=price, 
        passenger_count=1, 
        scheduled_time=data.get('scheduled_time'), 
        from_lat=data.get('from_lat'), 
        from_lon=data.get('from_lon'), 
        car_class=data.get('car_class', 'Standard'),
        order_type='parcel',
        parcel_photo=photo_id
    )
    
    confirm_msg = f"<b>✅ Buyurtma yuborildi!</b>\n\n{get_trans(lang, 'passenger_warning_order')}"
    await message.answer(
        confirm_msg,
        reply_markup=await get_passenger_menu(has_active_order=True, lang=lang),
        parse_mode="HTML"
    )
    
    from handlers.driver import broadcast_order
    asyncio.create_task(broadcast_order(
        message.bot, order_id, from_loc, full_to_loc, 
        price, 1, data.get('scheduled_time', "Hozir"), 
        data.get('from_lat'), data.get('from_lon'), data.get('car_class', 'Standard'),
        parcel_photo=photo_id,
        order_type='parcel'
    ))
    
    await state.update_data(current_order_id=order_id)
    await state.set_state(ParcelProcess.waiting_for_driver)
    asyncio.create_task(wait_for_drivers_task(message.bot, message.from_user.id, order_id, state, order_type='parcel'))
