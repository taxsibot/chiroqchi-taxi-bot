import time
from aiogram import types, BaseMiddleware
from aiogram.fsm.context import FSMContext
from typing import Any, Awaitable, Callable, Dict

from utils.cache import AUTO_REPLY_CACHE, AUTO_REPLY_CACHE_TTL

async def _get_auto_replies() -> dict[str, str]:
    """Return auto-reply dict from cache, refreshing if stale."""
    global AUTO_REPLY_CACHE
    # Import here to avoid circular at module load
    from utils.cache import AUTO_REPLY_CACHE as _arc
    import utils.cache as _cache_mod
    now = time.time()
    if (now - _cache_mod.AUTO_REPLY_CACHE[0]) < AUTO_REPLY_CACHE_TTL:
        return _cache_mod.AUTO_REPLY_CACHE[1]

    # Reload from DB
    from database.db import db_session
    replies: dict[str, str] = {}
    try:
        async with db_session() as db:
            async with db.execute("SELECT keyword, reply FROM auto_replies") as cursor:
                rows = await cursor.fetchall()
                replies = {row[0].lower(): row[1] for row in rows}
    except Exception:
        pass
    _cache_mod.AUTO_REPLY_CACHE = (now, replies)
    return replies


class AutoReplyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Only text messages in private chats
        if not isinstance(event, types.Message) or not event.text:
            return await handler(event, data)
        if event.chat.type != "private":
            return await handler(event, data)
        # Skip commands
        if event.text.startswith("/"):
            return await handler(event, data)

        # Skip main menu buttons and common greetings to let core handlers work
        from utils.state_guard import MAIN_MENU_BUTTONS
        import re
        
        text_lower = event.text.lower().strip()
        # Clean the input text for comparison (remove emojis and leading symbols)
        msg_clean = re.sub(r'^[^\w\s]+\s*', '', event.text).strip()
        
        greetings = {"salom", "assalom", "assalomu alaykum", "hello", "hi", "привет", "здравствуйте"}
        
        # Check if it's a menu button (either literal or cleaned)
        is_menu_btn = event.text in MAIN_MENU_BUTTONS or text_lower in MAIN_MENU_BUTTONS
        if not is_menu_btn:
            # Check cleaned versions
            for btn in MAIN_MENU_BUTTONS:
                if not btn: continue
                btn_clean = re.sub(r'^[^\w\s]+\s*', '', btn).strip()
                if msg_clean == btn_clean or event.text == btn:
                    is_menu_btn = True
                    break

        if text_lower in greetings or is_menu_btn:
            return await handler(event, data)

        # Check auto-replies using memory cache (no DB call per message)
        replies = await _get_auto_replies()
        if replies:
            text_lower = event.text.lower().strip()
            
            # 1. Look for specific keyword matches
            matched_reply = None
            for keyword, reply in replies.items():
                if keyword == "*" or keyword == "default":
                    continue
                if keyword in text_lower:
                    matched_reply = reply
                    break
            
            # 2. Handle state-dependent logic
            state: FSMContext = data.get("state")
            current_state = await state.get_state() if state else None
            
            # CRITICAL FIX: If user is in an active FSM state, do NOT auto-reply.
            # This ensures registration, ordering, etc. are not interrupted by keywords.
            if current_state is not None:
                return await handler(event, data)

            if matched_reply:
                await event.answer(matched_reply, parse_mode="HTML")
                return  # Stop propagation
            
            # 3. Fallback logic: Only if NO state is active (redundant but safe)
            matched_reply = replies.get("*") or replies.get("default")
            if matched_reply:
                await event.answer(matched_reply, parse_mode="HTML")
                return  # Stop propagation

        return await handler(event, data)
