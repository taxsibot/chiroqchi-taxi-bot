import asyncio
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_order, get_user_language
import logging
from utils.locales import get_trans
from utils.states import OrderProcess, ParcelProcess

logger = logging.getLogger(__name__)

async def wait_for_drivers_task(bot: Bot, passenger_id: int, order_id: int, state: FSMContext, order_type: str = 'taxi'):
    """Wait and notify periodically if no driver accepted."""
    attempts = 0
    max_attempts = 3 # Total wait time approx 4.5 minutes
    
    while attempts < max_attempts:
        await asyncio.sleep(90) # Wait 90 seconds per attempt
        
        order = await get_order(order_id)
        # If order is no longer pending, stop the task
        if not order or order[11] != 'pending':
            return
            
        lang = await get_user_language(passenger_id)
        attempts += 1
        
        text = (
            f"<b>⏳ {get_trans(lang, 'no_driver_found')} ({attempts}/{max_attempts})</b>\n\n"
            f"💰 Narx: {int(order[5]):,} so'm\n\n"
            f"Haydovchilar qidirilmoqda... Narxni oshirsangiz haydovchi tezroq topilishi mumkin."
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Narxni oshirish", callback_data=f"up_p_{order_id}")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"c_o_{order_id}")]
        ])
        
        try:
            await bot.send_message(passenger_id, text, reply_markup=kb, parse_mode="HTML")
            # Note: State setting removed to prevent overwriting active user flow. (L-3)
        except Exception as e:
            logger.error(f"Failed to send wait message #{attempts} for order #{order_id}: {e}")
            break # If user blocked bot, stop task
