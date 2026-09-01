from aiogram import BaseMiddleware, Router, F, Bot
from aiogram.types import Message, ChatMemberUpdated, ChatJoinRequest, InlineKeyboardMarkup, InlineKeyboardButton
from typing import Any, Callable, Dict, Awaitable
from database.db import add_group, delete_group, has_user_started, mark_user_started, remove_user_started
import time
import logging

logger = logging.getLogger(__name__)
router = Router()

# Cache structure: {chat_id: {"title": "Group Title", "timestamp": 123456789}}
_GROUP_CACHE: Dict[int, Dict[str, Any]] = {}
_CACHE_TTL = 3600  # 1 hour cache TTL

# Ogohlantirish yuborilgan foydalanuvchilarni keshlaymiz (spam oldini olish)
_WARNED_USERS: Dict[int, float] = {}
_WARN_COOLDOWN = 60  # 60 soniya oraliqda bir marta ogohlantirish


class GroupTrackerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        if event.chat.type in ["group", "supergroup"]:
            chat_id = event.chat.id
            title = event.chat.title
            now = time.time()

            # Guruh ma'lumotini DB ga saqlash (kesh bilan)
            cached = _GROUP_CACHE.get(chat_id)
            if not cached or cached["title"] != title or (now - cached["timestamp"]) > _CACHE_TTL:
                await add_group(chat_id, title)
                _GROUP_CACHE[chat_id] = {"title": title, "timestamp": now}

        return await handler(event, data)


# ─── 1. JOIN REQUEST (Avtomatik guruhga qabul qilish va Lichkaga xabar yuborish) ───

@router.chat_join_request()
async def auto_approve_join_request(event: ChatJoinRequest, bot: Bot):
    """
    Foydalanuvchi guruhga a'zo bo'lish so'rovini (Join Request) yuborganida:
    1. Avtomatik tarzda guruhga qabul qiladi (approve).
    2. Bot bazasiga (bot_starters) saqlaydi.
    3. Foydalanuvchining lichkasiga xush kelibsiz xabari va taksi/pochta tugmalarini yuboradi.
    """
    user = event.from_user
    chat = event.chat
    
    # 1. Guruhga avtomatik qabul qilish
    try:
        await event.approve()
        logger.info(f"✅ Auto-approved join request: User {user.id} ({user.full_name}) in group '{chat.title}'")
    except Exception as e:
        logger.warning(f"Could not approve join request for user {user.id}: {e}")

    # 2. Bazaga saqlash
    await mark_user_started(user.id)
    if chat.title:
        await add_group(chat.id, chat.title)

    # 3. Foydalanuvchining shaxsiyiga (lichkasiga) bot xabarini yuborish
    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username or "chiroqchitaksibot"
    except Exception:
        bot_username = "chiroqchitaksibot"

    welcome_text = (
        f"👋 <b>Assalomu alaykum, {user.full_name}!</b>\n\n"
        f"✅ Siz <b>{chat.title or 'Taksi'}</b> guruhiga muvaffaqiyatli qabul qilindingiz!\n\n"
        f"🚕 <b>Bizning rasmiy botimiz orqali:</b>\n"
        f"• Qulay narxlarda tezkor taksi chaqirishingiz\n"
        f"• Toshkent ⇄ Qashqadaryo bo'ylab pochta yuborishingiz\n"
        f"• Yoki haydovchi bo'lib buyurtmalarni olishingiz mumkin!\n\n"
        f"👇 <i>Kerakli bo'limni tanlang:</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚕 Taksi chaqirish", url=f"https://t.me/{bot_username}?start=new")],
        [InlineKeyboardButton(text="📦 Pochta yuborish", url=f"https://t.me/{bot_username}?start=parcel")],
        [InlineKeyboardButton(text="🚗 Haydovchi bo'lib ishlash", url=f"https://t.me/{bot_username}?start=driver")],
        [InlineKeyboardButton(text="🤖 Botga kirish", url=f"https://t.me/{bot_username}?start=main")]
    ])

    try:
        await bot.send_message(user.id, welcome_text, reply_markup=kb, parse_mode="HTML")
        logger.info(f"Sent welcome DM to join-request user {user.id}")
    except Exception as e:
        logger.debug(f"Could not send DM to join-request user {user.id}: {e}")


# ─── 2. BOT GURUHDAN CHIQARILGANDA / QO'SHILGANDA ───────────────────────────

@router.my_chat_member()
async def on_my_chat_member_update(update: ChatMemberUpdated):
    """
    Tracks when:
    - Bot guruhga qo'shiladi yoki chiqariladi
    - Foydalanuvchi botni bloklaydi (kicked) yoki blokdan ochadi (member)
    """
    chat_id = update.chat.id
    chat_type = update.chat.type
    user_id = update.from_user.id

    # Guruh holati
    if chat_type in ["group", "supergroup", "channel"]:
        title = update.chat.title or ""
        if update.new_chat_member.status in ["member", "administrator"]:
            await add_group(chat_id, title)
            _GROUP_CACHE[chat_id] = {"title": title, "timestamp": time.time()}
            logger.info(f"Bot added to group: {title} ({chat_id})")
        elif update.new_chat_member.status in ["left", "kicked"]:
            await delete_group(chat_id)
            if chat_id in _GROUP_CACHE:
                del _GROUP_CACHE[chat_id]
            logger.info(f"Bot removed from group: {title} ({chat_id})")
        return

    # Private chat — foydalanuvchi botni blokladi/blokdan ochdi
    new_status = update.new_chat_member.status
    if new_status == "kicked":
        # Foydalanuvchi botni blokladi → bot_starters dan o'chiramiz
        await remove_user_started(user_id)
        logger.info(f"User {user_id} blocked the bot — removed from bot_starters")
    elif new_status == "member":
        # Foydalanuvchi botni blokdan ochdi → bot_starters ga qayta qo'shamiz
        await mark_user_started(user_id)
        logger.info(f"User {user_id} unblocked the bot — added back to bot_starters")
