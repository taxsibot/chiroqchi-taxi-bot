from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.states import SupportStates
from database.db import get_user_language, log_action
from utils.locales import get_trans
from utils.utils import IsMenuButton
from config import ADMIN_ID

router = Router()

# --- USER SIDE ---

@router.message(IsMenuButton('write_admin'))
async def support_start(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    await state.clear() # Clear any existing state first
    await state.set_state(SupportStates.waiting_for_message)
    # Initialize empty history
    await state.update_data(ai_history=[])
    
    text = get_trans(lang, 'support_title')
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_trans(lang, 'cancel'), callback_data="cancel_support")]
    ])
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "cancel_support")
async def cancel_support(callback: types.CallbackQuery, state: FSMContext):
    lang = await get_user_language(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text(f"❌ {get_trans(lang, 'cancel')}")

@router.callback_query(F.data == "finish_support")
async def finish_support(callback: types.CallbackQuery, state: FSMContext):
    lang = await get_user_language(callback.from_user.id)
    await state.clear()
    thanks_msg = "Sizga yordam berganimdan xursandman! ✨\nBoshqa savollar bo'lsa, istalgan vaqtda yozishingiz mumkin. Xayr! 👋"
    if lang == 'ru':
        thanks_msg = "Рад был вам помочь! ✨\nЕсли возникнут вопросы, пишите в любое время. До свидания! 👋"
    
    await callback.message.edit_text(thanks_msg, parse_mode="HTML")
    await callback.answer()

@router.message(SupportStates.waiting_for_message)
async def process_support_message(message: types.Message, state: FSMContext):
    # Fail-safe: if the message is a menu button, it should have been caught by middleware.
    from utils.state_guard import MAIN_MENU_BUTTONS
    if message.text in MAIN_MENU_BUTTONS:
        await state.clear()
        return
    
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    username = message.from_user.username or "N/A"
    full_name = message.from_user.full_name
    
    # --- AI ASSISTANT INTEGRATION ---
    from database.db import get_setting
    ai_enabled = await get_setting('ai_support_enabled', '0')
    
    if ai_enabled == '1' and message.text:
        from utils.ai_helper import get_ai_response
        waiting_msg = await message.answer("🤖 <i>AI Yordamchi o'ylamoqda...</i>", parse_mode="HTML")
        
        # Get history from state
        data = await state.get_data()
        history = data.get('ai_history', [])
        
        ai_response, updated_history = await get_ai_response(message.text, history, lang)
        
        try:
            await waiting_msg.delete()
        except:
            pass
        
        if ai_response:
            # Update history in state
            await state.update_data(ai_history=updated_history)
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👨‍💻 Adminga o'tish (Murojaat qilish)", callback_data="send_to_admin_manual")],
                [InlineKeyboardButton(text="✅ Rahmat, suhbatni tugatish", callback_data="finish_support")]
            ])
            await message.answer(
                f"🤖 <b>AI Yordamchi:</b>\n\n{ai_response}",
                reply_markup=kb, parse_mode="HTML"
            )
            # Store message text in state in case they want to send to admin
            await state.update_data(support_msg_text=message.text)
            
            # STATE CLEAR QILINMAYDI - Suhbat davom etadi!
            return

    # If AI is disabled or failed to respond, proceed to admin
    await send_support_to_admin(message, state)

async def send_support_to_admin(message: types.Message, state: FSMContext, manual_text: str = None):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    username = message.from_user.username or "N/A"
    full_name = message.from_user.full_name
    text_to_send = manual_text if manual_text else message.text

    import html
    safe_name = html.escape(full_name)
    safe_username = html.escape(username)
    
    admin_header = (
        f"📩 <b>YANGI MUROJAAT</b>\n\n"
        f"👤 <b>Kimdan:</b> {safe_name} (@{safe_username})\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"support_reply_{user_id}")]
    ])
    
    try:
        await message.bot.send_message(ADMIN_ID, admin_header, parse_mode="HTML")
        if manual_text:
            await message.bot.send_message(ADMIN_ID, manual_text, reply_markup=keyboard)
        else:
            await message.copy_to(ADMIN_ID, reply_markup=keyboard)
            
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Suhbatni tugatish", callback_data="finish_support")]
        ])
        await message.answer(
            f"✅ Murojaat adminga yuborildi. Endi siz to'g'ridan-to'g'ri admin bilan suhbatlashyapsiz.\n"
            f"Xabar yozishda davom etishingiz mumkin.", 
            reply_markup=kb
        )
        
        # O'zgartirish: Userni admin bilan suhbat rejimiga o'tkazamiz
        await state.set_state(SupportStates.chatting_with_admin)
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")
        await state.clear()

@router.callback_query(F.data == "send_to_admin_manual")
async def send_to_admin_manual_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_text = data.get('support_msg_text')
    try:
        try:
            await callback.message.delete()
        except:
            pass
    except:
        pass
    await send_support_to_admin(callback.message, state, manual_text=msg_text)
    await callback.answer()

@router.message(SupportStates.chatting_with_admin)
async def process_user_chat_to_admin(message: types.Message, state: FSMContext):
    """User adminga to'g'ridan-to'g'ri yozyapti"""
    from utils.state_guard import MAIN_MENU_BUTTONS
    if message.text in MAIN_MENU_BUTTONS:
        await state.clear()
        return
        
    user_id = message.from_user.id
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"support_reply_{user_id}")]
    ])
    
    try:
        await message.copy_to(ADMIN_ID, reply_markup=keyboard)
    except Exception as e:
        await message.answer(f"❌ Yuborishda xatolik: {e}")

# --- ADMIN SIDE ---

@router.callback_query(F.data.startswith("support_reply_"), F.from_user.id == ADMIN_ID)
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext):
    target_user_id = int(callback.data.split("_")[2])
    await state.update_data(reply_to_user_id=target_user_id)
    await state.set_state(SupportStates.waiting_for_reply)
    
    await callback.message.answer(
        f"✍️ ID <code>{target_user_id}</code> bo'lgan foydalanuvchiga javob yozyapsiz.\n"
        f"Har bir yozgan xabaringiz unga yetib boradi.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Suhbatni tugatish", callback_data="cancel_admin_reply")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "cancel_admin_reply", F.from_user.id == ADMIN_ID)
async def cancel_admin_reply(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Foydalanuvchi bilan suhbat tugatildi.")

@router.message(SupportStates.waiting_for_reply, F.from_user.id == ADMIN_ID)
async def process_admin_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_user_id = data.get('reply_to_user_id')
    
    if not target_user_id:
        return await state.clear()
        
    try:
        # Prepend a header only for text messages if desired, but easiest is to send a header then copy the message
        # But to avoid spamming "ADMIN JAVOBI" every time, we just copy. Or we can just copy.
        # Let's send header if it's text.
        if message.text:
            await message.bot.send_message(target_user_id, f"👨‍💻 <b>ADMIN:</b> {message.html_text}", parse_mode="HTML")
        else:
            await message.bot.send_message(target_user_id, "👨‍💻 <b>ADMIN:</b>", parse_mode="HTML")
            await message.copy_to(target_user_id)
            
        await message.answer(f"✅ Javob yuborildi.")
        await log_action(ADMIN_ID, "support_reply", f"Replied to user {target_user_id}")
        # STATE CLEAR QILINMAYDI - Admin ham yozishda davom etishi mumkin
    except Exception as e:
        await message.answer(f"❌ Xatolik: Foydalanuvchi botni bloklagan bo'lishi mumkin.\n{e}")
        await state.clear()
