from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_logs
from .base import admin_filter
from datetime import datetime

router = Router()

@router.callback_query(F.data == "adm_logs", admin_filter)
async def adm_logs_menu(callback: types.CallbackQuery):
    await callback.answer()
    
    logs = await get_logs(limit=20)
    
    text = "<b>📝 TIZIM LOGLARI (Oxirgi 20 ta)</b>\n━━━━━━━━━━━━━━\n\n"
    
    if logs:
        for log in logs:
            # log: 0=id, 1=admin_id, 2=action, 3=details, 4=timestamp
            try:
                dt = datetime.fromisoformat(log[4].replace("Z", "+00:00"))
                ts_str = dt.strftime("%d.%m %H:%M")
            except:
                ts_str = str(log[4])[:16]
                
            text += f"🔹 <b>{log[2]}</b> <i>({ts_str})</i>\n└ <code>{log[3]}</code>\n\n"
    else:
        text += "<i>Hozircha tizimda loglar yo'q.</i>"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="adm_logs")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")]
    ])
    
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        # Avoid error if text hasn't changed on refresh
        pass
