from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from database.db import (
    create_order, get_user, add_user, update_order_price, 
    get_passenger_id_by_order_id, update_order_status, get_order, get_user_language, 
    get_setting, get_passenger_active_orders, get_online_driver_ids, get_driver_active_orders,
    get_passenger_pending_orders, save_user_address, get_saved_addresses
)

from utils.utils import IsMenuButton
from utils.states import OrderProcess
from keyboards.reply import get_passenger_menu, get_passenger_count_keyboard, get_driver_menu
from utils.order_helpers import wait_for_drivers_task
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, ContentType
from utils.locales import get_trans
from utils.route_helper import get_estimated_price
from config import ADMIN_ID
import asyncio
import json
import re
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
router = Router()


from utils.route_helper import get_location_keyboard, get_estimated_price
from database.db import (
    get_active_rides, get_ride, book_ride_seats, get_user_ride_bookings, cancel_ride_booking
)

# --- 💺 HAMROH / POPUTCHIK REYSLARI (Yo'lovchi uchun) ---

@router.message(F.chat.type == "private", IsMenuButton('rides_btn'))
@router.message(F.chat.type == "private", F.text.in_({"💺 Hamroh / Reyslar", "💺 Попутчик / Рейсы", "/rides"}))
async def show_rides_list(message: types.Message):
    lang = await get_user_language(message.from_user.id)
    rides = await get_active_rides(limit=8)
    
    if not rides:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Yangilash", callback_data="refresh_rides")],
            [InlineKeyboardButton(text="📋 Mening bronlarim", callback_data="my_ride_bookings")]
        ])
        return await message.answer(
            f"<b>💺 HAMROH / SHAHARLARARO REYSLAR</b>\n━━━━━━━━━━━━━━\n\n"
            f"{get_trans(lang, 'no_active_rides')}\n\n"
            f"<i>Shaharlararo qatnovchi haydovchilar reys e'lon qilganda shu yerda ko'rinadi.</i>",
            reply_markup=kb, parse_mode="HTML"
        )
    
    text = (
        f"<b>💺 FAOL SHAHARLARARO REYSLAR</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"Kerakli reysni tanlab, o'rindiq sonini belgilang:\n\n"
    )
    
    buttons = []
    for r in rides:
        ride_id, driver_id, from_loc, to_loc, dep_time, total_seats, avail_seats, price_seat, car_model, car_number, notes, created_at, driver_name, driver_phone, rating = r
        d_rating = f"⭐ {rating:.1f}" if rating else "⭐ 5.0"
        
        text += (
            f"🚘 <b>{car_model}</b> (<code>{car_number}</code>) | {d_rating}\n"
            f"👤 Haydovchi: {driver_name}\n"
            f"📍 <b>{from_loc} ➡️ {to_loc}</b>\n"
            f"⏰ Jo'nash: <b>{dep_time}</b>\n"
            f"💺 Bo'sh joy: <b>{avail_seats} ta</b> | 💰 <b>{int(price_seat):,} so'm</b>/joy\n"
        )
        if notes:
            text += f"💬 <i>{notes}</i>\n"
        text += "━━━━━━━━━━━━━━\n"
        
        row = []
        for s in range(1, min(avail_seats + 1, 4)):
            row.append(InlineKeyboardButton(text=f"💺 {s} ta joy (#{ride_id})", callback_data=f"bookride_{ride_id}_{s}"))
        buttons.append(row)
        
    buttons.append([
        InlineKeyboardButton(text="🔄 Yangilash", callback_data="refresh_rides"),
        InlineKeyboardButton(text="📋 Mening bronlarim", callback_data="my_ride_bookings")
    ])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data == "refresh_rides")
async def refresh_rides_cb(callback: types.CallbackQuery):
    await callback.answer("Yangilandi 🔄")
    try: await callback.message.delete()
    except: pass
    await show_rides_list(callback.message)

@router.callback_query(F.data.startswith("bookride_"))
async def process_book_ride(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    ride_id = int(parts[1])
    seats = int(parts[2])
    passenger_id = callback.from_user.id
    
    lang = await get_user_language(passenger_id)
    success, result = await book_ride_seats(ride_id, passenger_id, seats)
    
    if not success:
        return await callback.answer(f"❌ {result}", show_alert=True)
        
    ride = await get_ride(ride_id)
    if not ride:
        return await callback.answer("Reys ma'lumotlari topilmadi.", show_alert=True)
        
    # ride structure: ride_id, driver_id, from_loc, to_loc, dep_time, total, avail, price, model, plate, notes, status, created, driver_name, driver_phone, rating
    driver_id = ride[1]
    from_loc = ride[2]
    to_loc = ride[3]
    dep_time = ride[4]
    price_seat = ride[7]
    car_model = ride[8]
    car_plate = ride[9]
    driver_name = ride[13]
    driver_phone = ride[14]
    total_price = int(price_seat * seats)
    
    # 1. Notify Passenger
    pass_text = (
        f"✅ <b>REYS MUVAFFAQIYATLI BAND QILINDI!</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"📍 <b>Yo'nalish:</b> {from_loc} ➡️ {to_loc}\n"
        f"⏰ <b>Jo'nash vaqti:</b> {dep_time}\n"
        f"💺 <b>Band qilingan joy:</b> {seats} ta\n"
        f"💰 <b>Jami to'lov:</b> {total_price:,} so'm\n"
        f"━━━━━━━━━━━━━━\n"
        f"🚘 <b>Mashina:</b> {car_model} (<code>{car_plate}</code>)\n"
        f"👤 <b>Haydovchi:</b> {driver_name}\n"
        f"📞 <b>Telefon:</b> {driver_phone}\n\n"
        f"<i>Iltimos, belgilangan vaqtdan oldinroq haydovchi bilan bog'laning!</i>"
    )
    await callback.message.edit_text(pass_text, parse_mode="HTML")
    await callback.answer("✅ Bron muvaffaqiyatli amalga oshirildi!", show_alert=True)
    
    # 2. Notify Driver
    try:
        passenger_user = await get_user(passenger_id)
        p_name = passenger_user[1] if passenger_user else callback.from_user.full_name
        p_phone = passenger_user[2] if passenger_user else "Noma'lum"
        
        driver_alert = (
            f"🎉 <b>YANGI HAMROH BRON QILDI!</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"📍 <b>Reys:</b> {from_loc} ➡️ {to_loc} ({dep_time})\n"
            f"👤 <b>Yo'lovchi:</b> {p_name}\n"
            f"📞 <b>Telefon:</b> <code>{p_phone}</code>\n"
            f"💺 <b>Band joy soni:</b> {seats} ta\n"
            f"💰 <b>To'lov:</b> <b>{total_price:,} so'm</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"Qolgan bo'sh joylar: <b>{ride[6]} ta</b>"
        )
        await callback.bot.send_message(driver_id, driver_alert, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error notifying driver of ride booking: {e}")

@router.callback_query(F.data == "my_ride_bookings")
async def show_my_bookings(callback: types.CallbackQuery):
    await callback.answer()
    passenger_id = callback.from_user.id
    bookings = await get_user_ride_bookings(passenger_id)
    
    if not bookings:
        return await callback.message.answer(
            "📋 <b>Sizda hozircha faol reys bronlari mavjud emas.</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Ortga", callback_data="refresh_rides")]])
        )
        
    text = "<b>📋 MENING REYS BRONLARIM:</b>\n━━━━━━━━━━━━━━\n\n"
    buttons = []
    for b in bookings:
        b_id, ride_id, seats, b_time, f_loc, t_loc, dep_time, price, model, plate, d_name, d_phone = b
        text += (
            f"🚘 <b>{f_loc} ➡️ {t_loc}</b>\n"
            f"⏰ Vaqt: <b>{dep_time}</b>\n"
            f"💺 Joy: <b>{seats} ta</b> | 💰 <b>{int(price*seats):,} so'm</b>\n"
            f"👤 Haydovchi: {d_name} (📞 <code>{d_phone}</code>)\n"
            f"🚗 Mashina: {model} (<code>{plate}</code>)\n"
            f"━━━━━━━━━━━━━━\n"
        )
        buttons.append([InlineKeyboardButton(text=f"❌ Bekor qilish (#{b_id})", callback_data=f"cancel_booking_{b_id}")])
        
    buttons.append([InlineKeyboardButton(text="🔙 Barcha reyslar", callback_data="refresh_rides")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data.startswith("cancel_booking_"))
async def process_cancel_booking(callback: types.CallbackQuery):
    b_id = int(callback.data.split("_")[2])
    success = await cancel_ride_booking(b_id, callback.from_user.id)
    if success:
        await callback.answer("✅ Bron bekor qilindi.", show_alert=True)
        await show_my_bookings(callback)
    else:
        await callback.answer("❌ Bekor qilib bo'lmadi.", show_alert=True)

@router.message(F.chat.type == "private", IsMenuButton('radar_btn'))
async def start_radar(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📍 " + get_trans(lang, 'share_live_location'), request_location=True)],
        [KeyboardButton(text=get_trans(lang, 'back'))]
    ], resize_keyboard=True)
    await message.answer(get_trans(lang, 'share_location_radar'), reply_markup=kb, parse_mode="HTML")
    await state.set_state(OrderProcess.wait_for_location)

@router.message(OrderProcess.wait_for_location, F.location)
async def process_radar_location(message: types.Message, state: FSMContext):
    from database.db import get_nearby_drivers
    lang = await get_user_language(message.from_user.id)
    
    lat = message.location.latitude
    lon = message.location.longitude
    
    drivers = await get_nearby_drivers(lat, lon, radius_km=20.0)
    
    if not drivers:
        await message.answer("😔 20km radiusda onlayn haydovchilar topilmadi.", reply_markup=await get_passenger_menu(lang=lang))
        await state.clear()
        return
        
    text = get_trans(lang, 'nearby_drivers_title')
    for d in drivers:
        uid, name, car, plate, d_lat, d_lon, rating, dist = d
        text += f"🚗 <b>{car}</b> ({plate})\n└ 👤 {name} | ⭐ {rating:.1f} | 📍 {dist:.1f} km\n\n"
        
    await message.answer(text, reply_markup=await get_passenger_menu(lang=lang), parse_mode="HTML")
    await state.clear()

@router.message(F.content_type == ContentType.WEB_APP_DATA)
async def process_web_app_data(message: types.Message, state: FSMContext):
    try:
        data = json.loads(message.web_app_data.data)
    except Exception as e:
        logger.error(f"Error parsing webapp data: {e}")
        return
        
    lang = await get_user_language(message.from_user.id)
    action = data.get('action', '')
    
    if action in ['order_taxi', 'webapp_order']:
        from_loc = data.get('from') or data.get('from_loc', '')
        to_loc = data.get('to') or data.get('to_loc', '')
        raw_price = float(data.get('price', 0))
        p_count = int(data.get('passengers', 1))
        car_class = data.get('tariff', 'Standard')
        if car_class not in ['Standard', 'Comfort']:
            car_class = 'Standard'
        order_type = 'parcel' if data.get('tariff') == 'parcel' else 'taxi'
        
        if raw_price <= 0:
            raw_price = await get_estimated_price(from_loc, to_loc, car_class)
            
        surge_mult = await get_setting('surge_multiplier', '1.0')
        final_price = int(raw_price * float(surge_mult))
            
        order_id = await create_order(
            passenger_id=message.from_user.id,
            from_loc=from_loc,
            to_loc=to_loc,
            price=final_price,
            passenger_count=p_count,
            car_class=car_class,
            order_type=order_type,
            scheduled_time="Hozir"
        )
        
        await message.answer(
            f"✅ <b>WEB ILOVA ORQALI BUYURTMA QABUL QILINDI!</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"🔢 <b>Buyurtma ID:</b> #{order_id}\n"
            f"📍 <b>Qayerdan:</b> {from_loc}\n"
            f"🏁 <b>Qayerga:</b> {to_loc}\n"
            f"🚗 <b>Tarif:</b> {'✨ Komfort' if car_class=='Comfort' else ('📦 Pochta' if order_type=='parcel' else '🚙 Standart')}\n"
            f"💰 <b>Narxi:</b> <b>{final_price:,} so'm</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"<i>Haydovchilar qidirilmoqda...</i>",
            reply_markup=await get_passenger_menu(has_active_order=True, lang=lang),
            parse_mode="HTML"
        )
        
        await state.update_data(current_order_id=order_id)
        from handlers.driver import broadcast_order
        asyncio.create_task(broadcast_order(message.bot, order_id, from_loc, to_loc, final_price, p_count, car_class=car_class, order_type=order_type))
        asyncio.create_task(wait_for_drivers_task(message.bot, message.from_user.id, order_id, state, order_type=order_type))


async def show_order_confirm_card(target, state: FSMContext, user_id: int, is_edit: bool = False):
    data = await state.get_data()
    from_loc = data.get('from_loc', 'Chiroqchi')
    to_loc = data.get('to_loc', 'Toshkent')
    p_count = int(data.get('passengers', 1))
    car_class = data.get('car_class', 'Standard')
    sched_time = data.get('scheduled_time', 'Hozir')
    
    price = data.get('price')
    if not price:
        price = await get_estimated_price(from_loc, to_loc, car_class=car_class)
        await state.update_data(price=price)
        
    class_name = "✨ Komfort" if car_class == 'Comfort' else "🚙 Standart"
    
    text = (
        f"🚕 <b>BUYURTMANI TASDIQLASH</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"📍 <b>Qayerdan:</b> {from_loc}\n"
        f"🏁 <b>Qayerga:</b> {to_loc}\n"
        f"👥 <b>Yo'lovchi:</b> {p_count} kishi\n"
        f"🚗 <b>Tarif:</b> {class_name}\n"
        f"💰 <b>Narxi:</b> <b>{int(price):,} so'm</b>\n"
        f"⏰ <b>Vaqt:</b> {sched_time}\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>Buyurtmani haydovchilarga yuboramizmi?</i>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Buyurtma berish", callback_data="confirm_taxi_order_now")],
        [
            InlineKeyboardButton(text=f"{'🔘 ' if p_count==1 else ''}1 kishi", callback_data="pax_set_1"),
            InlineKeyboardButton(text=f"{'🔘 ' if p_count==2 else ''}2 kishi", callback_data="pax_set_2"),
            InlineKeyboardButton(text=f"{'🔘 ' if p_count==3 else ''}3 kishi", callback_data="pax_set_3"),
            InlineKeyboardButton(text=f"{'🔘 ' if p_count==4 else ''}4 kishi", callback_data="pax_set_4"),
        ],
        [
            InlineKeyboardButton(text="➕ 10 000", callback_data="price_adj_up_10000"),
            InlineKeyboardButton(text="➖ 10 000", callback_data="price_adj_down_10000"),
            InlineKeyboardButton(text="✏️ Narx kiritish", callback_data="price_adj_custom")
        ],
        [
            InlineKeyboardButton(text="✨ Komfort (+20%)" if car_class=='Standard' else "🚙 Standart", callback_data="toggle_car_class"),
        ],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_order_creation")]
    ])
    
    if is_edit:
        try:
            await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except:
            pass
    await target.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(F.chat.type == "private", IsMenuButton('order_taxi'))
async def start_order(message: types.Message, state: FSMContext, user_id: int = None):
    uid = user_id or message.from_user.id
    lang = await get_user_language(uid)
    await state.clear()
    await state.set_state(OrderProcess.entering_from)
    await state.update_data(passengers=1, car_class='Standard', scheduled_time='Hozir')
    
    q_text = get_trans(lang, 'where_from')
    kb = await get_location_keyboard("from", uid, lang=lang)
    await message.answer(
        f"📍 <b>{q_text}</b>\n<i>Quyidagi ro'yxatdan tanlang yoki manzilni yozing:</i>",
        reply_markup=kb, parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("loc_"))
async def process_location_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    step = parts[1] # 'from' or 'to'
    place = "_".join(parts[2:])
    lang = await get_user_language(callback.from_user.id)
    
    if place == "none":
        return await callback.answer()
        
    if parts[1] == "back":
        await state.clear()
        await callback.message.delete()
        return await callback.answer("Bekor qilindi.")
        
    if place == "custom":
        q_text = get_trans(lang, f'where_{step}')
        await callback.message.edit_text(f"✏️ <b>{q_text}</b>\n<i>Manzil nomini yozib yuboring:</i>", parse_mode="HTML")
        await state.set_state(OrderProcess.entering_from if step == 'from' else OrderProcess.entering_to)
        return await callback.answer()

    if step == 'from':
        await state.update_data(from_loc=place)
        await save_user_address(callback.from_user.id, place)
        await state.set_state(OrderProcess.entering_to)
        q_text = get_trans(lang, 'where_to')
        kb = await get_location_keyboard("to", callback.from_user.id, lang=lang)
        await callback.message.edit_text(
            f"📍 Qayerdan: <b>{place}</b>\n\n🏁 <b>{q_text}</b>\n<i>Boradigan manzilni tanlang:</i>",
            reply_markup=kb, parse_mode="HTML"
        )
    else:
        await state.update_data(to_loc=place)
        await save_user_address(callback.from_user.id, place)
        await show_order_confirm_card(callback.message, state, callback.from_user.id, is_edit=True)
    
    await callback.answer()


@router.message(OrderProcess.entering_from, F.text)
async def process_from_text(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    if message.text == get_trans(lang, 'back'):
        await state.clear()
        return await message.answer(get_trans(lang, 'cancel'), reply_markup=await get_passenger_menu(lang=lang))
    
    await state.update_data(from_loc=message.text)
    await save_user_address(message.from_user.id, message.text)
    await state.set_state(OrderProcess.entering_to)
    q_text = get_trans(lang, 'where_to')
    kb = await get_location_keyboard("to", message.from_user.id, lang=lang)
    await message.answer(
        f"📍 Qayerdan: <b>{message.text}</b>\n\n🏁 <b>{q_text}</b>\n<i>Boradigan manzilni tanlang:</i>",
        reply_markup=kb, parse_mode="HTML"
    )


@router.message(OrderProcess.entering_to, F.text)
async def process_to_text(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    if message.text == get_trans(lang, 'back'):
        await state.set_state(OrderProcess.entering_from)
        q_text = get_trans(lang, 'where_from')
        kb = await get_location_keyboard("from", message.from_user.id, lang=lang)
        return await message.answer(f"📍 {q_text}", reply_markup=kb, parse_mode="HTML")
    
    await state.update_data(to_loc=message.text)
    await save_user_address(message.from_user.id, message.text)
    await show_order_confirm_card(message, state, message.from_user.id, is_edit=False)


# ─── Instant Interactive Order Card Modifiers ──────────────────────────────

@router.callback_query(F.data.startswith("pax_set_"))
async def process_pax_set(callback: types.CallbackQuery, state: FSMContext):
    count = int(callback.data.split("_")[2])
    await state.update_data(passengers=count)
    await show_order_confirm_card(callback.message, state, callback.from_user.id, is_edit=True)
    await callback.answer(f"{count} kishi")


@router.callback_query(F.data.startswith("price_adj_"))
async def process_price_adj(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.replace("price_adj_", "")
    data = await state.get_data()
    price = int(data.get("price", 50000))
    
    if action == "up_10000":
        price += 10000
        await state.update_data(price=price)
        await show_order_confirm_card(callback.message, state, callback.from_user.id, is_edit=True)
        await callback.answer(f"Narx: {price:,} so'm")
    elif action == "down_10000":
        price = max(10000, price - 10000)
        await state.update_data(price=price)
        await show_order_confirm_card(callback.message, state, callback.from_user.id, is_edit=True)
        await callback.answer(f"Narx: {price:,} so'm")
    elif action == "custom":
        await state.set_state(OrderProcess.entering_price)
        await callback.message.answer("✏️ <i>O'zingiz xohlagan narxni kiriting (masalan: 120000):</i>", parse_mode="HTML")
        await callback.answer()


@router.message(OrderProcess.entering_price, F.text)
async def process_custom_price_text(message: types.Message, state: FSMContext):
    price_str = re.sub(r'[^\d]', '', message.text)
    if not price_str:
        return await message.answer("❌ Faqat raqam kiriting (masalan: 100000):")
    price = int(price_str)
    if price < 5000:
        return await message.answer("❌ Minimal narx 5,000 so'm!")
        
    await state.update_data(price=price)
    await show_order_confirm_card(message, state, message.from_user.id, is_edit=False)


@router.callback_query(F.data == "toggle_car_class")
async def process_toggle_car_class(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    curr_class = data.get('car_class', 'Standard')
    new_class = 'Comfort' if curr_class == 'Standard' else 'Standard'
    
    from_loc = data.get('from_loc', 'Chiroqchi')
    to_loc = data.get('to_loc', 'Toshkent')
    new_price = await get_estimated_price(from_loc, to_loc, car_class=new_class)
    
    await state.update_data(car_class=new_class, price=new_price)
    await show_order_confirm_card(callback.message, state, callback.from_user.id, is_edit=True)
    await callback.answer(f"Tarif: {'✨ Komfort' if new_class=='Comfort' else '🚙 Standart'}")


@router.callback_query(F.data == "cancel_order_creation")
async def process_cancel_order_creation(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass
    lang = await get_user_language(callback.from_user.id)
    await callback.message.answer("❌ Buyurtma bekor qilindi.", reply_markup=await get_passenger_menu(lang=lang))
    await callback.answer("Bekor qilindi.")


@router.callback_query(F.data == "confirm_taxi_order_now")
async def process_confirm_taxi_order_now(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    from_loc = data.get('from_loc', 'Chiroqchi')
    to_loc = data.get('to_loc', 'Toshkent')
    price = int(data.get('price', 50000))
    p_count = int(data.get('passengers', 1))
    car_class = data.get('car_class', 'Standard')
    sched_time = data.get('scheduled_time', 'Hozir')
    lang = await get_user_language(callback.from_user.id)

    order_id = await create_order(
        passenger_id=callback.from_user.id,
        from_loc=from_loc,
        to_loc=to_loc,
        price=price,
        passenger_count=p_count,
        scheduled_time=sched_time,
        car_class=car_class,
        order_type='taxi'
    )

    class_label = "✨ Komfort" if car_class == 'Comfort' else "🚙 Standart"

    await callback.message.edit_text(
        f"✅ <b>BUYURTMA MUVAFFAQIYATLI YARATILDI!</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔢 <b>Buyurtma ID:</b> #{order_id}\n"
        f"📍 <b>Qayerdan:</b> {from_loc}\n"
        f"🏁 <b>Qayerga:</b> {to_loc}\n"
        f"👥 <b>Yo'lovchilar:</b> {p_count} ta\n"
        f"🚗 <b>Tarif:</b> {class_label}\n"
        f"💰 <b>Narxi:</b> <b>{price:,} so'm</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>Haydovchilar va guruhlarga yuborildi. Kuting...</i>",
        parse_mode="HTML"
    )

    await callback.message.answer(
        get_trans(lang, 'order_received_wait'),
        reply_markup=await get_passenger_menu(has_active_order=True, lang=lang)
    )

    await state.update_data(current_order_id=order_id)
    await state.set_state(OrderProcess.waiting_for_driver)

    from handlers.driver import broadcast_order
    asyncio.create_task(broadcast_order(
        callback.bot, order_id, from_loc, to_loc, price,
        p_count, sched_time, car_class=car_class, order_type='taxi'
    ))
    asyncio.create_task(wait_for_drivers_task(callback.bot, callback.from_user.id, order_id, state, order_type='taxi'))
    await callback.answer("Buyurtma yuborildi 🚀")


@router.message(F.chat.type == "private", IsMenuButton('active_order_manage'))
async def manage_order(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    orders = await get_passenger_active_orders(message.from_user.id)
    if not orders:
        pending = await get_passenger_pending_orders(message.from_user.id)
        if not pending: return await message.answer(get_trans(lang, 'no_active_orders'))
        orders = pending
        
    for order in orders:
        order_id = order[0]
        status = order[11]
        kb_list = []
        if status in ['accepted', 'arrived']:
            kb_list.append([InlineKeyboardButton(text=get_trans(lang, 'chat_with_driver'), callback_data=f"chat_{order_id}")])
            kb_list.append([InlineKeyboardButton(text=get_trans(lang, 'cancel'), callback_data=f"cancel_order_{order_id}")])
        else:
            kb_list.append([InlineKeyboardButton(text=get_trans(lang, 'cancel'), callback_data=f"cancel_order_{order_id}")])
            kb_list.append([InlineKeyboardButton(text=get_trans(lang, 'raise_price'), callback_data=f"up_p_{order_id}")])
            
        kb = InlineKeyboardMarkup(inline_keyboard=kb_list)
        status_text = get_trans(lang, f'status_{status}') if get_trans(lang, f'status_{status}') else status
        text = (
            f"🚕 <b>Buyurtma #{order_id}</b>\n"
            f"{get_trans(lang, 'order_status_label').format(status=status_text)}\n"
            f"{order[3]} ➔ {order[4]}"
        )
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ─── Narxni oshirish (up_p_) ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("up_p_"))
async def raise_price_inline(callback: types.CallbackQuery, state: FSMContext):
    """
    'Narxni oshirish' tugmasi bosilganda:
    1. DB'dagi narxni +10 000 so'm oshiradi
    2. Guruhga qayta broadcast qiladi
    3. Foydalanuvchiga yangi narxni ko'rsatadi
    """
    order_id = int(callback.data.split("_")[2])
    order = await get_order(order_id)
    lang = await get_user_language(callback.from_user.id)

    if not order or order[11] != 'pending':
        await callback.answer("❌ Buyurtma topilmadi yoki allaqachon bajarilgan.", show_alert=True)
        return

    # Faqat buyurtma egasi o'zgartira oladi
    if order[1] != callback.from_user.id:
        return await callback.answer("⛔ Bu sizning buyurtmangiz emas!", show_alert=True)

    old_price = int(order[5])
    step = int(await get_setting('price_raise_step', '10000'))
    new_price = old_price + step

    # DB yangilaymiz
    await update_order_price(order_id, new_price)

    # Guruhga qayta broadcast
    from handlers.driver import broadcast_order
    asyncio.create_task(
        broadcast_order(
            callback.bot,
            order_id,
            order[3],   # from_loc
            order[4],   # to_loc
            new_price,
            order[6],   # passenger_count
            order[7],   # scheduled_time
            is_update=True
        )
    )

    # Xabarni yangilaymiz
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_trans(lang, 'raise_price'), callback_data=f"up_p_{order_id}")],
        [InlineKeyboardButton(text=get_trans(lang, 'cancel'), callback_data=f"c_o_{order_id}")]
    ])
    
    await callback.message.edit_text(
        f"{get_trans(lang, 'price_updated')}\n\n"
        f"📍 {order[3]} ➔ {order[4]}\n"
        f"💰 {get_trans(lang, 'wallet_balance').format(balance=new_price)}\n\n"
        f"Haydovchilar qayta xabardor qilindi...",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer(f"✅ {new_price:,} so'm")


# ─── Bidding (ab_ / rb_) ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ab_"))
async def accept_bid_handler(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    driver_id = int(parts[1])
    order_id = int(parts[2])
    amount = float(parts[3])
    lang = await get_user_language(callback.from_user.id)
    
    order = await get_order(order_id)
    if not order or order[11] != 'pending':
        return await callback.answer("⚠️ Buyurtma allaqachon bajarilgan yoki bekor qilingan.", show_alert=True)
        
    if order[1] != callback.from_user.id:
        return await callback.answer("⛔ Bu sizning buyurtmangiz emas!", show_alert=True)

    await update_order_price(order_id, amount)
    
    from database.db import accept_order
    success, msg = await accept_order(order_id, driver_id)
    
    if success:
        try:
            await callback.message.edit_text(f"✅ Haydovchining {amount:,} so'mlik taklifi qabul qilindi!")
        except: pass
        
        from database.db import get_driver, get_user
        d_info = await get_driver(driver_id)
        u_info = await get_user(driver_id)
        import html
        safe_name = html.escape(u_info[1])
        safe_car = html.escape(d_info[1])
        text = get_trans(lang, 'order_found_passenger').format(
            name=safe_name,
            phone=u_info[2],
            car=safe_car,
            plate=d_info[2]
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚨 SOS", callback_data="sos_alert")]])
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        
        d_lang = await get_user_language(driver_id)
        acc_text = get_trans(d_lang, 'order_accepted_driver').format(order_id=order_id)
        acc_text += f"\n\n{get_trans(d_lang, 'driver_warning_accept')}"
        kb_list = [
            [InlineKeyboardButton(text=get_trans(d_lang, 'arrived'), callback_data=f"status_arrived_{order_id}")],
            [InlineKeyboardButton(text=get_trans(d_lang, 'finish'), callback_data=f"status_finished_{order_id}")],
        ]
        if await get_setting('btn_live_location', '1') == '1':
            kb_list.append([InlineKeyboardButton(text=get_trans(d_lang, 'share_live_location'), callback_data=f"live_loc_req_{order_id}")])
        if await get_setting('btn_chat', '1') == '1':
            kb_list.append([InlineKeyboardButton(text=get_trans(d_lang, 'chat_btn'), callback_data=f"chat_{order_id}")])
        kb_list.append([InlineKeyboardButton(text="🚨 SOS", callback_data="sos_alert")])
        
        try:
            await callback.bot.send_message(driver_id, acc_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list), parse_mode="HTML")
        except: pass
        
        await callback.answer("✅ Qabul qilindi!")
    else:
        await callback.answer(f"❌ Haydovchi bilan bog'lanib bo'lmadi: {msg}", show_alert=True)

@router.callback_query(F.data.startswith("rb_"))
async def reject_bid_handler(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except: pass
    await callback.answer("❌ Rad etildi")

# ─── Buyurtmani bekor qilish (c_o_) ─────────────────────────────────────────

@router.callback_query(F.data.startswith("c_o_"))
@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order_inline(callback: types.CallbackQuery, state: FSMContext):
    """Buyurtmani bekor qilish — DB'da 'cancelled' ga o'tkazadi."""
    raw = callback.data
    order_id = int(raw.split("_")[-1])
    order = await get_order(order_id)
    lang = await get_user_language(callback.from_user.id)

    if not order:
        return await callback.answer("❌ Buyurtma topilmadi.", show_alert=True)

    if order[1] != callback.from_user.id:
        return await callback.answer("⛔ Bu sizning buyurtmangiz emas!", show_alert=True)

    if order[11] not in ('pending', 'accepted', 'arrived'):
        return await callback.answer("⚠️ Buyurtma allaqachon yakunlangan.", show_alert=True)

    await update_order_status(order_id, 'cancelled')
    await state.clear()

    # Notify driver if one was assigned
    if order[2]:
        try:
            await callback.bot.send_message(
                order[2],
                f"⚠️ <b>Buyurtma #{order_id} mijoz tomonidan bekor qilindi.</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    try:
        await callback.message.edit_text(
            f"❌ <b>Buyurtma #{order_id} bekor qilindi.</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass


    user = await get_user(callback.from_user.id)
    await callback.message.answer(
        get_trans(lang, 'order_cancelled'),
        reply_markup=await get_passenger_menu(
            is_admin=(callback.from_user.id == ADMIN_ID),
            lang=lang
        ),
        parse_mode="HTML"
    )
    await callback.answer("❌ Bekor qilindi.")


@router.callback_query(F.data == "confirm_voice_order")
async def finalize_voice_order(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    voice_data = data.get('voice_order')
    if not voice_data: return await callback.answer("Error: Data lost.")
    
    import html
    from_loc = html.escape(voice_data['from_loc'])
    to_loc = html.escape(voice_data['to_loc'])
    price = voice_data['price']
    p_count = voice_data['passenger_count']
    
    order_id = await create_order(
        passenger_id=callback.from_user.id,
        from_loc=from_loc,
        to_loc=to_loc,
        price=price,
        passenger_count=p_count,
        scheduled_time="Hozir"
    )
    
    lang = await get_user_language(callback.from_user.id)
    await callback.message.edit_text(f"✅ <b>Ovozli buyurtma yaratildi!</b>\nID: #{order_id}", parse_mode="HTML")
    await callback.message.answer(get_trans(lang, 'order_received_wait'), reply_markup=await get_passenger_menu(has_active_order=True, lang=lang))
    
    from handlers.driver import broadcast_order
    asyncio.create_task(broadcast_order(callback.bot, order_id, from_loc, to_loc, price, p_count))
    asyncio.create_task(wait_for_drivers_task(callback.bot, callback.from_user.id, order_id, state))
    await callback.answer()
