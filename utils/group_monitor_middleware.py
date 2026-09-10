import asyncio
import logging
import time
from aiogram import BaseMiddleware, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import (
    is_group_guarded, has_user_started, get_user_language
)
from utils.locales import get_trans
from config import ADMIN_ID
from utils.cache import (
    USER_WARNING_COOLDOWN, CHAT_WARNING_COOLDOWN,
    USER_WARNING_TIME, CHAT_WARNING_TIME, WARNING_MESSAGES
)
from utils.utils import check_subscription

logger = logging.getLogger(__name__)

class GroupMonitorMiddleware(BaseMiddleware):
    """
    Middleware that monitors group messages for:
    1. Subscription Guard (Delete if not subbed or not started)
    2. Group Role Redirects (Optional, or handled by handlers)
    """
    
    def __init__(self):
        self.user_status_cache = {} # {(chat_id, user_id): (status, timestamp)}
        self.bot_permission_cache = {} # {chat_id: timestamp_of_failure}

    async def __call__(self, handler, event, data):
        if not isinstance(event, Message) or event.chat.type not in ["group", "supergroup"]:
            return await handler(event, data)

        message = event
        if not message.from_user or message.from_user.is_bot:
            return await handler(event, data)

        # A. Subscription Guard
        if await is_group_guarded(message.chat.id):
            now = time.time()
            is_exempt = message.from_user.id == ADMIN_ID
            
            if not is_exempt:
                cache_key = (message.chat.id, message.from_user.id)
                cached_status = self.user_status_cache.get(cache_key)
                
                if cached_status and (now - cached_status[1]) < 3600:
                    is_exempt = cached_status[0] in ["administrator", "creator"]
                else:
                    try:
                        member = await message.chat.get_member(message.from_user.id)
                        self.user_status_cache[cache_key] = (member.status, now)
                        if member.status in ["administrator", "creator"]:
                            is_exempt = True
                    except:
                        if message.sender_chat and message.sender_chat.id == message.chat.id:
                            is_exempt = True

            if not is_exempt:
                # Check registration and subscription
                has_started = await has_user_started(message.from_user.id)
                is_subscribed = True
                if has_started:
                    is_subscribed = await check_subscription(message.bot, message.from_user.id)

                if not has_started or not is_subscribed:
                    # Guard logic triggered
                    # Determine if bot can delete messages in this chat
                    bot_can_delete = False
                    try:
                        bot_me = await message.bot.get_me()
                        bot_member = await message.bot.get_chat_member(message.chat.id, bot_me.id)
                        # In Telegram, admin rights include can_delete_messages attribute
                        bot_can_delete = getattr(bot_member, "can_delete_messages", False)
                    except Exception:
                        # If we cannot determine, assume no delete permission
                        bot_can_delete = False
                    
                    recent_failure = self.bot_permission_cache.get(message.chat.id)
                    # If we previously detected unable to delete, respect cooldown
                    if recent_failure and (now - recent_failure) < 3600:
                        bot_can_delete = False
                    
                    if bot_can_delete:
                        try:
                            await message.delete()
                            # If deleted, we STOP propagation and send warning
                            await self._send_warning(message, has_started)
                            return 
                        except Exception as e:
                            msg_err = str(e).lower()
                            if "can't be deleted" in msg_err or "admin" in msg_err:
                                self.bot_permission_cache[message.chat.id] = now
                                logger.error(f"GUARD FAILURE: Bot cannot delete messages in {message.chat.id}")
                    # If bot cannot delete, just send warning without deleting
                    await self._send_warning(message, has_started)
                    return
                
        # If not deleted by guard, continue to handlers (e.g. Greeting handlers)
        return await handler(event, data)

    async def _send_warning(self, message, has_started):
        now = time.time()
        last_user_warn = USER_WARNING_COOLDOWN.get(message.from_user.id, 0)
        last_chat_warn = CHAT_WARNING_COOLDOWN.get(message.chat.id, 0)
        
        if (now - last_user_warn) < USER_WARNING_TIME or (now - last_chat_warn) < CHAT_WARNING_TIME:
            return

        bot_info = await message.bot.get_me()
        user_mention = message.from_user.mention_html()
        lang = await get_user_language(message.from_user.id)
        bot_username = bot_info.username or "chiroqchitaksibot"
        
        if not has_started:
            warn = get_trans(lang, 'group_warn_no_start').format(mention=user_mention, username=bot_username)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Botga kirish (/start)", url=f"https://t.me/{bot_username}?start=group")],
                [InlineKeyboardButton(text="🚕 Taksi chaqirish", url=f"https://t.me/{bot_username}?start=new")]
            ])
        else:
            warn = get_trans(lang, 'group_warn_no_sub').format(mention=user_mention, username=bot_username)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛡 Obuna bo'lish & Tekshirish", url=f"https://t.me/{bot_username}?start=sub")]
            ])
        
        try:
            msg = await message.answer(warn, reply_markup=kb, parse_mode="HTML")
            USER_WARNING_COOLDOWN[message.from_user.id] = now
            CHAT_WARNING_COOLDOWN[message.chat.id] = now
            
            async def delete_after(m, delay):
                await asyncio.sleep(delay)
                try: await m.delete()
                except: pass
            asyncio.create_task(delete_after(msg, 300)) # 5 minutdan keyin guruh toza qolishi uchun o'chirish
        except: pass

