from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.states import SupportStates
from database.db import get_user_language
from utils.locales import get_trans
from utils.utils import IsMenuButton
from utils.ai_helper import get_ai_response
import logging

router = Router()
logger = logging.getLogger(__name__)

from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter, or_f

class AIStates(StatesGroup):
    waiting_for_question = State()

@router.message(or_f(F.text.contains("AI Savol-Javob"), F.text.contains("AI Вопросы"), F.text.contains("AI Q&A"), IsMenuButton('ai_btn')))
async def ai_start(message: types.Message, state: FSMContext):
    from database.db import get_setting
    is_enabled = await get_setting('ai_support_enabled', '0')
    if is_enabled != '1':
        lang = await get_user_language(message.from_user.id)
        return await message.answer("⚠️ <b>AI tizimi hozircha o'chirilgan.</b>\nIltimos, keyinroq urinib ko'ring.", parse_mode="HTML")
        
    logger.info(f"AI session started for user {message.from_user.id}")
    lang = await get_user_language(message.from_user.id)
    await state.clear()
    await state.set_state(AIStates.waiting_for_question)
    await state.update_data(ai_history=[])
    
    text = get_trans(lang, 'ai_welcome')
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_trans(lang, 'cancel'), callback_data="cancel_ai")]
    ])
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "cancel_ai")
async def cancel_ai(callback: types.CallbackQuery, state: FSMContext):
    lang = await get_user_language(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text(f"❌ {get_trans(lang, 'cancel')}")
    await callback.answer()

@router.message(StateFilter(AIStates.waiting_for_question))
async def process_ai_question(message: types.Message, state: FSMContext):
    from utils.state_guard import MAIN_MENU_BUTTONS
    if message.text in MAIN_MENU_BUTTONS:
        await state.clear()
        # Pass to other handlers by not returning? No, we need to re-trigger.
        # But for now, just clearing state is fine, user can click again.
        return

    lang = await get_user_language(message.from_user.id)
    
    waiting_msg = await message.answer(get_trans(lang, 'ai_thinking'), parse_mode="HTML")
    
    data = await state.get_data()
    history = data.get('ai_history', [])
    
    ai_response, updated_history = await get_ai_response(message.text, history, lang)
    
    try:
        await waiting_msg.delete()
    except:
        pass
        
    if ai_response:
        await state.update_data(ai_history=updated_history)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Rahmat, tugatish", callback_data="cancel_ai")]
        ])
        await message.answer(
            f"🤖 <b>AI:</b>\n\n{ai_response}",
            reply_markup=kb, parse_mode="HTML"
        )
    else:
        await message.answer(get_trans(lang, 'ai_error'))
