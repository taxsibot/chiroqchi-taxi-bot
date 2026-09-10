from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from utils.ai_parser import parse_smart_order
from utils.locales import get_trans
from utils.route_helper import get_estimated_price
from database.db import get_user_language, create_order, get_setting
from keyboards.reply import get_passenger_menu
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import asyncio
import logging

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.chat.type == "private", F.text | F.voice)
async def handle_potential_smart_order(message: types.Message, state: FSMContext, bot: Bot):
    # Faqat hech qanday FSM holatida (state) bo'lmagan foydalanuvchilar uchun ishlaydi
    current_state = await state.get_state()
    if current_state is not None:
        return

    # Menyu tugmalarini va buyruqlarni e'tiborsiz qoldiramiz
    from utils.state_guard import MAIN_MENU_BUTTONS
    if message.text:
        if message.text.startswith("/") or message.text in MAIN_MENU_BUTTONS:
            return

    lang = await get_user_language(message.from_user.id)
    
    order_data = None
    voice_path = None

    if message.voice:
        status_msg = await message.answer("🎙 <i>Ovozingiz tahlil qilinmoqda...</i>", parse_mode="HTML")
        file_id = message.voice.file_id
        file = await bot.get_file(file_id)
        voice_path = f"temp/voice_{file_id}.ogg"
        os.makedirs("temp", exist_ok=True)
        await bot.download_file(file.file_path, voice_path)
        
        order_data = await parse_smart_order(voice_file_path=voice_path)
        if os.path.exists(voice_path):
            os.remove(voice_path)
        try:
            await status_msg.delete()
        except:
            pass
    else:
        order_data = await parse_smart_order(text=message.text)

    if not order_data or not order_data.get("is_order"):
        # Agar bu buyurtma bo'lmasa, ai_handler yoki umumiy yordamga o'tkazish
        return

    from_loc = order_data.get("from_loc", "Chiroqchi")
    to_loc = order_data.get("to_loc", "Toshkent")
    price = order_data.get("price")
    p_count = order_data.get("passengers", 1)
    o_type = order_data.get("order_type", "taxi")
    p_desc = order_data.get("parcel_description")

    # Narx aytilmagan bo'lsa, avtomatik tavsiya etilgan narxni hisoblash
    if not price or price <= 0:
        price = await get_estimated_price(from_loc, to_loc)
        order_data["price"] = price

    # Buyurtma ma'lumotlarini state'da saqlash
    await state.update_data(smart_order=order_data)

    order_icon = "🚕" if o_type == "taxi" else "📦"
    title = "TAKSI" if o_type == "taxi" else "POCHTA"
    dep_time = order_data.get('time') or "Hozir"
    dep_date = order_data.get('date') or "Bugun"
    
    msg_text = (
        f"🤖 <b>AQLLI {title} BUYURTMASI TUSHUNILDI!</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"📍 <b>Qayerdan:</b> <b>{from_loc}</b>\n"
        f"🏁 <b>Qayerga:</b> <b>{to_loc}</b>\n"
    )
    
    if o_type == "taxi":
        msg_text += f"👥 <b>Yo'lovchilar:</b> <b>{p_count} kishi</b>\n"
    else:
        msg_text += f"📦 <b>Yuk turi:</b> <b>{p_desc or 'Pochta / Posilka'}</b>\n"
        
    msg_text += (
        f"💰 <b>Narxi:</b> <b>{int(price):,} so'm</b>\n"
        f"⏰ <b>Vaqt:</b> {dep_date} ({dep_time})\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>Haydovchilarga efirga uzatamizmi?</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Tasdiqlash va E'lon qilish", callback_data="confirm_smart_order")],
        [
            InlineKeyboardButton(text="➕ 10 000", callback_data="smart_price_up_10000"),
            InlineKeyboardButton(text="➖ 10 000", callback_data="smart_price_down_10000")
        ],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_smart_order")]
    ])

    await message.answer(msg_text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("smart_price_"))
async def adjust_smart_price(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.replace("smart_price_", "") # up_10000 or down_10000
    data = await state.get_data()
    order_data = data.get("smart_order")
    if not order_data:
        return await callback.answer("Ma'lumotlar topilmadi.", show_alert=True)
        
    current_price = int(order_data.get("price", 50000))
    if "up" in action:
        current_price += 10000
    else:
        current_price = max(10000, current_price - 10000)
        
    order_data["price"] = current_price
    await state.update_data(smart_order=order_data)
    
    from_loc = order_data.get("from_loc", "Chiroqchi")
    to_loc = order_data.get("to_loc", "Toshkent")
    p_count = order_data.get("passengers", 1)
    o_type = order_data.get("order_type", "taxi")
    p_desc = order_data.get("parcel_description")
    dep_time = order_data.get('time') or "Hozir"
    dep_date = order_data.get('date') or "Bugun"
    title = "TAKSI" if o_type == "taxi" else "POCHTA"

    msg_text = (
        f"🤖 <b>AQLLI {title} BUYURTMASI TUSHUNILDI!</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"📍 <b>Qayerdan:</b> <b>{from_loc}</b>\n"
        f"🏁 <b>Qayerga:</b> <b>{to_loc}</b>\n"
    )
    if o_type == "taxi":
        msg_text += f"👥 <b>Yo'lovchilar:</b> <b>{p_count} kishi</b>\n"
    else:
        msg_text += f"📦 <b>Yuk turi:</b> <b>{p_desc or 'Pochta / Posilka'}</b>\n"
        
    msg_text += (
        f"💰 <b>Narxi:</b> <b>{int(current_price):,} so'm</b>\n"
        f"⏰ <b>Vaqt:</b> {dep_date} ({dep_time})\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>Haydovchilarga efirga uzatamizmi?</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Tasdiqlash va E'lon qilish", callback_data="confirm_smart_order")],
        [
            InlineKeyboardButton(text="➕ 10 000", callback_data="smart_price_up_10000"),
            InlineKeyboardButton(text="➖ 10 000", callback_data="smart_price_down_10000")
        ],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_smart_order")]
    ])
    
    await callback.message.edit_text(msg_text, reply_markup=kb, parse_mode="HTML")
    await callback.answer(f"Narx: {current_price:,} so'm")

@router.callback_query(F.data == "confirm_smart_order")
async def confirm_smart_order(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_data = data.get("smart_order")
    if not order_data:
        return await callback.answer("Ma'lumotlar topilmadi. Qaytadan yozing.", show_alert=True)

    lang = await get_user_language(callback.from_user.id)
    price = int(order_data.get("price", 50000))
    from_loc = order_data.get("from_loc", "Chiroqchi")
    to_loc = order_data.get("to_loc", "Toshkent")
    p_count = int(order_data.get("passengers", 1))
    o_type = order_data.get("order_type", "taxi")
    sched_time = f"{order_data.get('date', 'Bugun')} {order_data.get('time', 'Hozir')}"

    order_id = await create_order(
        passenger_id=callback.from_user.id,
        from_loc=from_loc,
        to_loc=to_loc,
        price=price,
        passenger_count=p_count,
        order_type=o_type,
        scheduled_time=sched_time
    )

    await callback.message.edit_text(
        f"🎉 <b>BUYURTMA QABUL QILINDI! (ID: #{order_id})</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"📍 {from_loc} ➔ {to_loc}\n"
        f"💰 Narxi: <b>{price:,} so'm</b>\n"
        f"⏰ Vaqt: {sched_time}\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>Haydovchilar va guruhlarga yuborildi. Kuting...</i>",
        parse_mode="HTML"
    )
    
    await callback.message.answer(
        get_trans(lang, 'order_received_wait'),
        reply_markup=await get_passenger_menu(has_active_order=True, lang=lang)
    )
    
    # Broadcast to all online drivers & all groups
    from handlers.driver import broadcast_order
    from utils.order_helpers import wait_for_drivers_task
    
    asyncio.create_task(broadcast_order(
        callback.bot, order_id, from_loc, to_loc, 
        price, p_count, sched_time, order_type=o_type
    ))
    asyncio.create_task(wait_for_drivers_task(callback.bot, callback.from_user.id, order_id, state, order_type=o_type))
    
    await state.clear()
    await callback.answer("Buyurtma yuborildi 🚀")

@router.callback_query(F.data == "cancel_smart_order")
async def cancel_smart_order(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except:
        pass
    await callback.answer("Bekor qilindi.")
