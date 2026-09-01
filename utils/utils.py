from aiogram import Bot
from aiogram.filters import BaseFilter
from aiogram.types import Message
from database.db import get_setting, get_active_channels, get_user_language
from utils.locales import get_trans
import re
import logging
from utils.cache import SUB_CACHE, CHANNELS_CACHE, CHANNELS_CACHE_TTL, CACHE_DURATION
import time

logger = logging.getLogger(__name__)

class IsMenuButton(BaseFilter):
    def __init__(self, key: str):
        self.key = key
        
    async def __call__(self, message: Message, lang: str = 'uz') -> bool:
        if not message.text: return False
        
        localized_text = get_trans(lang, self.key)
        
        # Clean both from emojis/leading symbols for better matching
        msg_clean = re.sub(r'^[^\w\s]+\s*', '', message.text).strip()
        loc_clean = re.sub(r'^[^\w\s]+\s*', '', localized_text).strip()
        
        match = msg_clean == loc_clean or localized_text == message.text
        logger.debug(f"IsMenuButton: key={self.key}, lang={lang}, msg='{message.text}', loc='{localized_text}', match={match}")
        return match

async def check_subscription(bot: Bot, user_id: int, bypass_cache: bool = False) -> bool:
    # 0. Check Cache
    now = time.time()
    if not bypass_cache and user_id in SUB_CACHE:
        # Use existing cache format from utils.cache if possible or unified one
        cached = SUB_CACHE[user_id]
        # Check if it's the new format (timestamp, is_sub) or old one from monitor.py
        if isinstance(cached, tuple) and len(cached) >= 2:
            # We'll use (timestamp, is_subscribed)
            ts, is_sub = cached[0], cached[1]
            cache_limit = 3600 if is_sub else 10 # 1 hour if subbed, 10 seconds if not
            if (now - ts) < cache_limit:
                return is_sub

    # Check if subscription is enabled
    sub_enabled = await get_setting('sub_enabled', '0')
    if sub_enabled == '0':
        return True
    
    from database.db import get_active_channels
    
    # 1. Get Channels
    c_list = await get_active_channels()
    
    if not c_list:
        return True
    
    is_subscribed = True
    for channel_id, _ in c_list:
        try:
            cid = str(channel_id).strip()
            member = await bot.get_chat_member(chat_id=cid, user_id=user_id)
            if member.status in ['left', 'kicked']:
                is_subscribed = False
                logger.info(f"User {user_id} is NOT subbed to {cid} (Status: {member.status})")
                break
        except Exception as e:
            if "chat not found" in str(e).lower():
                logger.warning(f"Channel {channel_id} not found. Please check if bot is admin and ID is correct.")
            else:
                logger.error(f"Error checking sub for {user_id} in {channel_id}: {e}")
            # Skip errors to not block users if one channel is misconfigured
            continue
            
    # Update Cache
    SUB_CACHE[user_id] = (now, is_subscribed)
    return is_subscribed

async def get_subscription_keyboard():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    active_channels = await get_active_channels()
    
    buttons = []
    for idx, channel in enumerate(active_channels):
        cid, url = channel
        if url and url.startswith("@"):
            url = f"https://t.me/{url[1:]}"
        
        # Try to make the button text more descriptive if possible
        btn_text = f"📢 {idx+1}-kanalga a'zo bo'lish"
        buttons.append([InlineKeyboardButton(text=btn_text, url=url)])
    
    buttons.append([InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub_again")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
