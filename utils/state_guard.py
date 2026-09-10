from aiogram import BaseMiddleware
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from typing import Callable, Any, Awaitable
from utils.locales import TRANSLATIONS
import logging
logger = logging.getLogger(__name__)

# List of all main menu button texts from all supported languages
# We manually collect these from locales.py to ensure the most robust detection.
MAIN_MENU_BUTTONS = set()

for lang in TRANSLATIONS.values():
    # Passenger buttons
    MAIN_MENU_BUTTONS.add(lang.get('order_taxi'))
    MAIN_MENU_BUTTONS.add(lang.get('order_parcel'))
    MAIN_MENU_BUTTONS.add(lang.get('rides_btn'))
    MAIN_MENU_BUTTONS.add(lang.get('radar_btn'))
    MAIN_MENU_BUTTONS.add(lang.get('my_orders'))
    MAIN_MENU_BUTTONS.add(lang.get('leaderboard'))
    MAIN_MENU_BUTTONS.add(lang.get('profile'))
    MAIN_MENU_BUTTONS.add(lang.get('write_admin'))
    MAIN_MENU_BUTTONS.add(lang.get('invite_friends'))
    MAIN_MENU_BUTTONS.add(lang.get('settings'))
    MAIN_MENU_BUTTONS.add(lang.get('add_group'))
    MAIN_MENU_BUTTONS.add(lang.get('manual'))
    MAIN_MENU_BUTTONS.add(lang.get('ai_btn'))
    MAIN_MENU_BUTTONS.add(lang.get('wallet'))
    
    MAIN_MENU_BUTTONS.add(lang.get('daily_bonus_btn'))
    MAIN_MENU_BUTTONS.add(lang.get('promo_btn'))
    MAIN_MENU_BUTTONS.add(lang.get('charity_btn'))
    MAIN_MENU_BUTTONS.add(lang.get('app_btn'))
    MAIN_MENU_BUTTONS.add(lang.get('cancel_order'))
    
    # Driver buttons
    MAIN_MENU_BUTTONS.add(lang.get('status_online'))
    MAIN_MENU_BUTTONS.add(lang.get('status_offline'))
    MAIN_MENU_BUTTONS.add(lang.get('create_ride_btn'))
    MAIN_MENU_BUTTONS.add(lang.get('return_trip_btn'))
    MAIN_MENU_BUTTONS.add(lang.get('driver_stats'))
    MAIN_MENU_BUTTONS.add(lang.get('route_settings'))
    MAIN_MENU_BUTTONS.add(lang.get('available_parcels'))


# Add hardcoded and special buttons from reply.py and handlers
HARDCODED_BUTTONS = {
    "🎁 Kunlik bonus", "🎁 Ежедневный бонус", "🎁 Daily Bonus",
    "🎫 Promokod", "🎫 Промокод", "🎫 Promocode",
    "❤️ Ehson", "❤️ Hayriya", "❤️ Благотворительность", "❤️ Charity",
    "➕ Guruhga qo'shish", "➕ Добавить в группу", "➕ Add to Group",
    "📖 Qo'llanma", "📖 Руководство", "📖 Manual",
    "🛠 Admin Panel", "🛣 Yo'nalish sozlash", "📱 Ilova", "🔄 Refresh",
    "💳 Hamyon", "💳 Кошелек", "💳 Wallet",
    "👥 Do'stlarni taklif qilish", "👥 Пригласить друзей", "👥 Invite Friends",
    "👨‍💻 Admin", "👨‍💻 Админ", "👨‍💻 Write to Admin",
    "✍️ Adminga yozish", "✍️ Написать админу", "✍️ Write to Admin",
    "❌ Bekor qilish", "❌ Отмена", "❌ Cancel",
    "🔙 Ortga", "🔙 Назад", "🔙 Back",
    "❌ Buyurtmani bekor qilish", "❌ Отменить заказ", "❌ Cancel Order"
}
MAIN_MENU_BUTTONS.update(HARDCODED_BUTTONS)

# Remove None values and empty strings BEFORE processing stripped buttons
MAIN_MENU_BUTTONS.discard(None)
MAIN_MENU_BUTTONS.discard("")

# Add versions without emojis just in case
STRIPPED_BUTTONS = {text.split(" ", 1)[1] for text in MAIN_MENU_BUTTONS if " " in text}
MAIN_MENU_BUTTONS.update(STRIPPED_BUTTONS)

class StateGuardMiddleware(BaseMiddleware):
    """
    Middleware that clears the FSM state if the message text matches any main menu button.
    This prevents the bot from getting 'stuck' in a state when the user wants to switch context.
    """
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any]
    ) -> Any:
        # We only care about text messages
        if not event.text:
            return await handler(event, data)
        
        # Check if the incoming text matches any known main menu button
        if event.text in MAIN_MENU_BUTTONS:
            state: FSMContext = data.get('state')
            if state:
                current_state = await state.get_state()
                if current_state is not None:
                    await state.clear()
        
        return await handler(event, data)
