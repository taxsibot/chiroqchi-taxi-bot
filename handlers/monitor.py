from aiogram import Router, F, types
from database.db import toggle_group_guard, is_group_guarded
from config import ADMIN_ID

router = Router()

# monitor.py is now mostly handled by GroupMonitorMiddleware.
# Any specific group commands or handlers can go here.

@router.callback_query(F.data.startswith("toggle_guard_"), F.from_user.id == ADMIN_ID)
async def admin_toggle_guard(callback: types.CallbackQuery):
    chat_id = int(callback.data.replace("toggle_guard_", ""))
    from database.db import toggle_group_guard
    new_status = await toggle_group_guard(chat_id)
    status_text = "Yoqildi" if new_status else "O'chirildi"
    await callback.answer(f"🛡 Guard: {status_text}")
    # Refresh the UI if possible
