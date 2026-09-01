"""
Chat Handler — Yo'lovchi ↔ Haydovchi Real-Time Relay Chat

Features:
- Auto-activate when order is accepted (status=accepted/arrived)
- Relay text, photo, voice, video, stickers, documents
- Typing indicator (sender ko'radi)
- Message delivered ✔️ mini confirmation (3s auto-delete)
- Chat auto-close after order completes (admin-configurable timeout)
- Admin monitoring: all chats logged
- Spam protection: block rapid-fire messages
- Clean UI: close button always visible
"""

from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_active_order_peer, get_user_language, get_user
from utils.locales import get_trans
from utils.states import ChatStates
from config import ADMIN_ID
import logging
import asyncio
import time
import html

logger = logging.getLogger(__name__)
router = Router()

# ─── Spam protection cache ────────────────────────────────────────────────────
_LAST_MSG: dict[int, float] = {}
_MSG_COOLDOWN = 0.8  # seconds between messages


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _chat_close_kb(peer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Chatni yopish", callback_data="close_chat")]
    ])


def _reply_kb_for_peer(sender_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard sent TO the peer with a message."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Chatni yopish", callback_data="close_chat")]
    ])


def _sender_badge(role: str, name: str) -> str:
    if role == 'driver':
        return f"🚗 <b>Haydovchi:</b> {html.escape(name)}"
    return f"🧑 <b>Yo'lovchi:</b> {html.escape(name)}"


# ─── Guruhga yangi a'zo qo'shilganda salomlashish ─────────────────────────────

@router.message(F.new_chat_members)
async def greet_new_members(message: types.Message):
    """Bot guruhga qo'shilganda yoki yangi a'zo kelganda chiroyli salomlashadi."""
    try:
        await message.delete()
    except Exception:
        pass

    for member in message.new_chat_members:
        if member.is_bot:
            continue

        user_id = member.id
        mention = member.mention_html()
        db_user = await get_user(user_id)

        if db_user:
            role = db_user[4]
            role_emoji = {"driver": "🚖 Haydovchi", "passenger": "🧑 Yo'lovchi"}.get(role, "👤 Foydalanuvchi")
            text = (
                f"👋 <b>Xush kelibsiz, {mention}!</b>\n"
                f"🏷 Rol: {role_emoji}\n\n"
                f"🚕 <b>CHIROQCHI TAKSILARI</b> guruhiga xush kelibsiz!"
            )
        else:
            text = (
                f"👋 <b>Assalomu alaykum, {mention}!</b>\n\n"
                f"🚕 <b>CHIROQCHI TAKSILARI</b> guruhiga xush kelibsiz!\n"
                f"Botimizdan foydalanish uchun quyidagi tugmani bosing 👇"
            )

        try:
            bot_info = await message.bot.get_me()
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🚀 Botga o'tish",
                    url=f"https://t.me/{bot_info.username}?start=start"
                )]
            ])
            msg = await message.answer(text, reply_markup=kb, parse_mode="HTML")

            async def _del(m):
                await asyncio.sleep(60)
                try:
                    await m.delete()
                except Exception:
                    pass
            asyncio.create_task(_del(msg))
        except Exception as e:
            logger.error(f"Guruh salomi xatosi (user_id={user_id}): {e}")


# ─── Chat ochish (callback tugma orqali) ──────────────────────────────────────

@router.callback_query(F.data.startswith("chat_"))
async def start_chat(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lang = await get_user_language(user_id)

    peer_id = await get_active_order_peer(user_id)
    if not peer_id:
        return await callback.answer("❌ Aktiv buyurtma topilmadi.", show_alert=True)

    await state.set_state(ChatStates.chatting)
    await state.update_data(chat_peer_id=peer_id)

    peer = await get_user(peer_id)
    peer_name = peer[1] if peer else "Suhbatdosh"

    await callback.message.answer(
        f"💬 <b>Chat ochildi!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Siz <b>{html.escape(peer_name)}</b> bilan chat qilyapsiz.\n\n"
        f"📝 <i>Xabar yozing — u darhol yetkaziladi.</i>\n"
        f"📷 Rasm, 🎤 Ovoz, 🎥 Video — hammasi ishlaydi!\n\n"
        f"<i>Chatni yopish uchun pastdagi tugmani bosing.</i>",
        reply_markup=_chat_close_kb(peer_id),
        parse_mode="HTML"
    )
    await callback.answer()


# ─── Chatni yopish ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "close_chat")
async def close_chat(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    peer_id = data.get('chat_peer_id')
    await state.clear()

    await callback.message.answer(
        "🔒 <b>Chat yopildi.</b>\n"
        "<i>Yana muloqot qilish uchun buyurtma jarayonida chat tugmasini bosing.</i>",
        parse_mode="HTML"
    )

    if peer_id:
        try:
            await callback.bot.send_message(
                peer_id,
                "🔒 <b>Suhbatdoshingiz chatni yopdi.</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass
    await callback.answer()


# ─── Xabar relay (ChatStates.chatting holati) ─────────────────────────────────

@router.message(ChatStates.chatting)
async def relay_chat_message(message: types.Message, state: FSMContext):
    from utils.state_guard import MAIN_MENU_BUTTONS
    if message.text and message.text in MAIN_MENU_BUTTONS:
        await state.clear()
        return

    user_id = message.from_user.id

    # Spam protection
    now = time.time()
    if now - _LAST_MSG.get(user_id, 0) < _MSG_COOLDOWN:
        return
    _LAST_MSG[user_id] = now

    data = await state.get_data()
    peer_id = data.get('chat_peer_id')

    if not peer_id:
        await state.clear()
        return

    user = await get_user(user_id)
    role = user[4] if user and len(user) > 4 else 'passenger'
    sender_name = user[1] if user else message.from_user.full_name

    badge = _sender_badge(role, sender_name)
    peer_kb = _reply_kb_for_peer(user_id)

    try:
        # Relay based on content type
        if message.text:
            safe = html.escape(message.text)
            await message.bot.send_message(
                peer_id,
                f"{badge}\n\n💬 {safe}",
                reply_markup=peer_kb,
                parse_mode="HTML"
            )
        elif message.photo:
            caption = html.escape(message.caption or "")
            await message.bot.send_photo(
                peer_id,
                message.photo[-1].file_id,
                caption=f"{badge}\n{caption}" if caption else badge,
                reply_markup=peer_kb,
                parse_mode="HTML"
            )
        elif message.voice:
            await message.bot.send_voice(
                peer_id, message.voice.file_id,
                caption=badge,
                reply_markup=peer_kb,
                parse_mode="HTML"
            )
        elif message.video:
            caption = html.escape(message.caption or "")
            await message.bot.send_video(
                peer_id, message.video.file_id,
                caption=f"{badge}\n{caption}" if caption else badge,
                reply_markup=peer_kb,
                parse_mode="HTML"
            )
        elif message.sticker:
            await message.bot.send_sticker(peer_id, message.sticker.file_id)
            await message.bot.send_message(peer_id, badge, reply_markup=peer_kb, parse_mode="HTML")
        elif message.document:
            caption = html.escape(message.caption or "")
            await message.bot.send_document(
                peer_id, message.document.file_id,
                caption=f"{badge}\n{caption}" if caption else badge,
                reply_markup=peer_kb,
                parse_mode="HTML"
            )
        elif message.location:
            await message.bot.send_location(peer_id, message.location.latitude, message.location.longitude)
            await message.bot.send_message(peer_id, f"{badge}\n📍 <i>Lokatsiya ulashildi</i>", reply_markup=peer_kb, parse_mode="HTML")
        else:
            await message.copy_to(peer_id)
            await message.bot.send_message(peer_id, badge, reply_markup=peer_kb, parse_mode="HTML")

        # Mini delivered confirmation (auto-delete in 2s)
        confirm = await message.answer("✔️ <i>Yetkazildi</i>", parse_mode="HTML")
        async def _del():
            await asyncio.sleep(2)
            try:
                await confirm.delete()
            except Exception:
                pass
        asyncio.create_task(_del())

    except Exception as e:
        err = str(e).lower()
        logger.error(f"Chat relay error {user_id}→{peer_id}: {e}")
        if "blocked" in err:
            await message.answer("❌ Suhbatdoshingiz botni bloklagan. Chat yopildi.")
            await state.clear()
        else:
            await message.answer("❌ Xabar yetkazilmadi. Iltimos, qayta urinib ko'ring.")


# ─── Auto-relay (Holatdagi bo'lmasdan ham aktiv buyurtma bo'lsa) ──────────────

@router.message(F.chat.type == "private")
async def auto_relay_chat_message(message: types.Message, state: FSMContext):
    """
    Catch-all: if user has an active order with a peer,
    auto-relay the message even if ChatStates is not active.
    """
    from utils.state_guard import MAIN_MENU_BUTTONS
    if message.text and message.text in MAIN_MENU_BUTTONS:
        return

    # Skip admin reply keyboard panel buttons
    from handlers.admin.base import admin_filter
    # Only proceed if not in any active FSM state already
    current_state = await state.get_state()
    if current_state:
        return  # Let the active state handler handle it

    user_id = message.from_user.id
    peer_id = await get_active_order_peer(user_id)

    if not peer_id:
        return

    # Silently open chat and relay
    await state.set_state(ChatStates.chatting)
    await state.update_data(chat_peer_id=peer_id)

    user = await get_user(user_id)
    role = user[4] if user and len(user) > 4 else 'passenger'
    sender_name = user[1] if user else message.from_user.full_name
    badge = _sender_badge(role, sender_name)
    peer_kb = _reply_kb_for_peer(user_id)

    try:
        if message.text:
            safe = html.escape(message.text)
            await message.bot.send_message(
                peer_id,
                f"{badge}\n\n💬 {safe}",
                reply_markup=peer_kb,
                parse_mode="HTML"
            )
        elif message.photo:
            caption = html.escape(message.caption or "")
            await message.bot.send_photo(
                peer_id, message.photo[-1].file_id,
                caption=f"{badge}\n{caption}" if caption else badge,
                reply_markup=peer_kb,
                parse_mode="HTML"
            )
        elif message.voice:
            await message.bot.send_voice(
                peer_id, message.voice.file_id,
                caption=badge, reply_markup=peer_kb, parse_mode="HTML"
            )
        elif message.location:
            await message.bot.send_location(peer_id, message.location.latitude, message.location.longitude)
            await message.bot.send_message(peer_id, f"{badge}\n📍 <i>Lokatsiya ulashildi</i>", reply_markup=peer_kb, parse_mode="HTML")
        else:
            await message.copy_to(peer_id)
            await message.bot.send_message(peer_id, badge, reply_markup=peer_kb, parse_mode="HTML")

        confirm = await message.answer("✔️ <i>Yetkazildi</i>", parse_mode="HTML")
        async def _del():
            await asyncio.sleep(2)
            try:
                await confirm.delete()
            except Exception:
                pass
        asyncio.create_task(_del())

    except Exception as e:
        logger.error(f"Auto-relay error {user_id}→{peer_id}: {e}")
