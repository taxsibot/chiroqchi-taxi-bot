from aiogram import Router, F, types
from database.db import get_top_drivers, get_user_language, add_rating, get_order
from utils.locales import get_trans
from utils.states import OrderProcess
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

@router.message(F.text.in_({"📊 Reyting", "📊 Рейтинг", "🏆 Leaderboard"}))
async def show_rating_board(message: types.Message):
    lang = await get_user_language(message.from_user.id)
    top_drivers = await get_top_drivers(limit=10)
    
    if not top_drivers:
        await message.answer(get_trans(lang, 'rating_empty'))
        return
        
    text = get_trans(lang, 'rating_title')
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, driver in enumerate(top_drivers):
        full_name, car_name, rating, total_rides = driver
        
        # Mask name for privacy (e.g. Ali V.)
        parts = full_name.split()
        d_name = full_name
        if len(parts) >= 2:
            d_name = f"{parts[0]} {parts[1][0]}."
            
        medal = medals[i] if i < len(medals) else "🔹"
        text += f"{medal} <b>{d_name}</b>\n└ 🚗 {car_name} | ⭐ {rating:.1f} | 🏁 {total_rides}\n\n"
        
    text += get_trans(lang, 'rating_footer')
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_profile")] 
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("rate_"))
async def process_rating(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    stars = int(parts[1])
    order_id = int(parts[2])
    
    order = await get_order(order_id)
    if not order: return await callback.answer("Error")
    
    await state.update_data(rating_stars=stars, rating_order_id=order_id, rating_driver_id=order[2], selected_badges=[])
    
    lang = await get_user_language(callback.from_user.id)
    
    # If stars >= 4, offer badges
    if stars >= 4:
        await show_badge_selection(callback, state)
    else:
        await state.set_state(OrderProcess.rating_driver)
        await callback.message.edit_text(
            get_trans(lang, 'rating_given').format(stars=stars) + "\n\n" + get_trans(lang, 'leave_feedback'),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_trans(lang, 'skip'), callback_data="skip_feedback")]
            ]),
            parse_mode="HTML"
        )
    await callback.answer(get_trans(lang, 'rating_success'))

async def show_badge_selection(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get('selected_badges', [])
    lang = await get_user_language(callback.from_user.id)
    
    def get_btn_text(key, label):
        return f"✅ {label}" if key in selected else label

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_btn_text('fast', '🏎 Tezkor'), callback_data="toggle_badge_fast")],
        [InlineKeyboardButton(text=get_btn_text('clean', '✨ Toza mashina'), callback_data="toggle_badge_clean")],
        [InlineKeyboardButton(text=get_btn_text('polite', '🤝 Xushmuomala'), callback_data="toggle_badge_polite")],
        [InlineKeyboardButton(text="➡️ Davom etish", callback_data="finish_badges")]
    ])
    
    msg_text = "<b>Haydovchiga nishon bering:</b>\n(Nimalar yoqqanini tanlang)"
    if callback.message.text == msg_text:
        await callback.message.edit_reply_markup(reply_markup=kb)
    else:
        await callback.message.edit_text(msg_text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("toggle_badge_"))
async def toggle_badge(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer() # Immediate feedback
    badge = callback.data.replace("toggle_badge_", "")
    data = await state.get_data()
    selected = data.get('selected_badges', [])
    
    if badge in selected:
        selected.remove(badge)
    else:
        selected.append(badge)
        
    await state.update_data(selected_badges=selected)
    await show_badge_selection(callback, state)

@router.callback_query(F.data == "finish_badges")
async def finish_badges(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderProcess.rating_driver)
    lang = await get_user_language(callback.from_user.id)
    data = await state.get_data()
    stars = data.get('rating_stars')
    
    if stars is None:
        return await callback.answer("Error: Data lost.", show_alert=True)

    await callback.message.edit_text(
        get_trans(lang, 'rating_given').format(stars=stars) + "\n\n" + get_trans(lang, 'leave_feedback'),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_trans(lang, 'skip'), callback_data="skip_feedback")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "skip_feedback")
async def skip_feedback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    stars = data.get('rating_stars')
    order_id = data.get('rating_order_id')
    driver_id = data.get('rating_driver_id')
    
    if None in (stars, order_id, driver_id):
        await state.clear()
        return await callback.answer("Error: Data lost.", show_alert=True)

    badges = ",".join(data.get('selected_badges', []))
    
    success = await add_rating(order_id, callback.from_user.id, driver_id, stars, badges=badges)
    lang = await get_user_language(callback.from_user.id)
    if success:
        await callback.message.edit_text(get_trans(lang, 'rating_success'))
    else:
        await callback.message.edit_text("⚠️ Siz ushbu buyurtmani allaqachon baholagansiz.")
    await state.clear()
    await callback.answer()

@router.message(OrderProcess.rating_driver, F.text)
async def process_feedback_comment(message: types.Message, state: FSMContext):
    data = await state.get_data()
    stars = data.get('rating_stars')
    order_id = data.get('rating_order_id')
    driver_id = data.get('rating_driver_id')
    
    if None in (stars, order_id, driver_id):
        await state.clear()
        return
        
    badges = ",".join(data.get('selected_badges', []))
    
    comment = message.text
    success = await add_rating(order_id, message.from_user.id, driver_id, stars, comment, badges)
    
    lang = await get_user_language(message.from_user.id)
    if success:
        await message.answer(get_trans(lang, 'feedback_success'))
    else:
        await message.answer("⚠️ Siz ushbu buyurtmani allaqachon baholagansiz.")
    await state.clear()

@router.message(OrderProcess.rating_driver)
async def process_feedback_invalid(message: types.Message):
    lang = await get_user_language(message.from_user.id)
    await message.answer(get_trans(lang, 'skip') + " — Iltimos, faqat matn yozing yoki o'tkazib yuboring.")
