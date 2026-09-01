from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Any, Awaitable, Union
from utils.utils import check_subscription, get_subscription_keyboard
from utils.cache import SUB_CACHE, CALLBACK_CACHE_DURATION
from config import ADMIN_ID
import time
import logging
logger = logging.getLogger(__name__)

class MandatorySubscriptionMiddleware(BaseMiddleware):
    """
    Middleware that enforces mandatory channel subscription for all private chat interactions.
    If the user is not subscribed to all active channels, they are prompted to do so.
    Exceptions:
      - /start command (always allowed)
      - lang_XX callbacks (language selection during registration)
      - check_sub_again callback (subscription re-check)
      - Any Registration:* FSM state (full registration flow allowed unblocked)
      - Callback queries use a longer cache TTL (10 min) to avoid excessive API calls
    """
    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: dict[str, Any]
    ) -> Any:
        # Only check in private chats
        chat = None
        if isinstance(event, Message):
            chat = event.chat
            user_id = event.from_user.id
            text = event.text or ""
            is_callback = False
        elif isinstance(event, CallbackQuery):
            chat = event.message.chat if event.message else None
            user_id = event.from_user.id
            text = event.data or ""
            is_callback = True
        else:
            return await handler(event, data)

        if not chat or chat.type != "private":
            return await handler(event, data)

        # Admins are always exempt
        if user_id == ADMIN_ID:
            return await handler(event, data)

        # Always allow /start command
        if isinstance(event, Message) and text.startswith("/start"):
            return await handler(event, data)

        # Always allow language selection callbacks (lang_uz, lang_ru, lang_en)
        if isinstance(event, CallbackQuery) and text.startswith("lang_"):
            return await handler(event, data)

        # Always allow subscription re-check callback
        if isinstance(event, CallbackQuery) and text == "check_sub_again":
            return await handler(event, data)

        # For callback queries: use a longer TTL cache to avoid API spam on every button press
        if is_callback:
            now = time.time()
            cached = SUB_CACHE.get(user_id)
            if cached and isinstance(cached, tuple) and len(cached) >= 2:
                ts, is_sub = cached[0], cached[1]
                if (now - ts) < CALLBACK_CACHE_DURATION:
                    # If they were subscribed (or sub check disabled), allow through
                    if is_sub:
                        return await handler(event, data)
                    # If they were NOT subscribed, only re-check after message TTL
                    # (they should re-verify via message, not every button press)
                    # For callbacks, just show the alert and don't re-check API
                    await event.answer(
                        "⚠️ Iltimos, avval kanallarga obuna bo'ling!", show_alert=True
                    )
                    return
            # No cache → fall through to full check below

        # ✅ CRITICAL FIX: Skip subscription check if user is in a Registration FSM state.
        state = data.get("state")
        if state:
            try:
                current_state = await state.get_state()
                if current_state and current_state.startswith("Registration:"):
                    logger.debug(
                        f"SubscriptionMiddleware: Skipping check for user {user_id} "
                        f"in Registration state '{current_state}'"
                    )
                    return await handler(event, data)
            except Exception:
                pass

        # Perform subscription check (with TTL caching in check_subscription)
        is_subscribed = await check_subscription(event.bot, user_id)
        logger.debug(
            f"SubscriptionMiddleware: user={user_id}, "
            f"text='{text[:50]}', is_subscribed={is_subscribed}"
        )

        if not is_subscribed:
            keyboard = await get_subscription_keyboard()
            warning_text = (
                "<b>ℹ️ BOTDAN FOYDALANISH UCHUN</b>\n\n"
                "Iltimos, botdan to'liq foydalanish va buyurtmalar berish uchun "
                "quyidagi kanallarga a'zo bo'ling:"
            )

            if isinstance(event, Message):
                await event.answer(warning_text, reply_markup=keyboard, parse_mode="HTML")
            else:
                await event.answer(
                    "⚠️ Iltimos, avval kanallarga obuna bo'ling!", show_alert=True
                )
                try:
                    await event.message.edit_text(
                        warning_text, reply_markup=keyboard, parse_mode="HTML"
                    )
                except Exception:
                    pass

            logger.debug(f"SubscriptionMiddleware: Blocking user {user_id}")
            return  # Stop execution

        return await handler(event, data)
