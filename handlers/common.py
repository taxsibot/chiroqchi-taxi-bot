import asyncio
import re
from aiogram import Router, F, types
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatMemberUpdated, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from database.db import (
    get_user_language, check_claim_daily_bonus, validate_and_use_promocode, 
    get_user, get_setting, add_group, delete_group, toggle_group_guard, 
    is_group_guarded, get_active_order_peer, get_order, update_order_price,
    get_passenger_active_orders, update_order_status, get_driver,
    add_charity_donation, get_charity_donors, remove_user_started, update_user_balance,
    get_active_targeted_charities, get_targeted_charity, update_charity_amount,
    add_charity_receipt, get_users_list, update_setting # Assume get_users_list exists for broadcast
)
from utils.locales import get_trans
from utils.states import PaymentStates, OrderProcess, ParcelProcess, Emergency
from keyboards.reply import get_passenger_menu, get_driver_menu
from utils.utils import check_subscription, get_subscription_keyboard, IsMenuButton
from utils.cache import USER_WARNING_COOLDOWN, CHAT_WARNING_COOLDOWN, USER_WARNING_TIME, CHAT_WARNING_TIME
from config import ADMIN_ID
import logging

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.chat.type == "private", F.text.lower().in_({
    "salom", "assalom", "assalomu alaykum", "hello", "hi", "привет", "здравствуйте"
}))
async def persistent_greeting(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user or not user[4]: # If no user or no role chosen
        from handlers.registration import cmd_start
        return await cmd_start(message, state)
    
    lang = user[8] or 'uz'
    role = user[4]
    name = message.from_user.first_name
    is_admin = user_id == ADMIN_ID
    
    text = get_trans(lang, 'greeting_reply').format(name=name)
    
    if role == 'passenger':
        menu = await get_passenger_menu(is_admin=is_admin, lang=lang)
    else:
        dr = await get_driver(user_id)
        # dr[6] is is_online status
        menu = await get_driver_menu(is_online=dr[6] if dr else False, is_admin=is_admin, lang=lang)
        
    await message.answer(text, reply_markup=menu, parse_mode="HTML")

@router.message(F.chat.type == "private", F.text.in_({"➕ Guruhga qo'shish", "➕ Добавить в группу", "➕ Add to Group"}))
async def add_to_group(message: types.Message):
    lang = await get_user_language(message.from_user.id)
    bot_info = await message.bot.get_me()
    
    text = get_trans(lang, 'add_group_info')
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_trans(lang, 'add_group_btn'), url=f"https://t.me/{bot_info.username}?startgroup=true")],
        [InlineKeyboardButton(text="📢 Share", url=f"https://t.me/share/url?url=https://t.me/{bot_info.username}")],
        [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_profile")]
    ])
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(F.chat.type == "private", IsMenuButton('invite_friends'))
@router.message(F.chat.type == "private", F.text.in_({"👥 Do'stlarni taklif qilish", "👥 Пригласить друзей", "👥 Invite Friends", "/invite"}))
async def invite_friends_handler(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    bot_info = await message.bot.get_me()
    
    from database.db import get_referral_stats, get_setting
    ref_count = await get_referral_stats(user_id)
    ref_bonus = int(await get_setting('ref_bonus', '500'))
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    
    text = (
        f"<b>🎁 DO'STARNI TAKLIF QILING VA PUL ISHLANG!</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"Do'stlaringizni botimizga taklif qiling va har bir taklif qilingan do'stingiz uchun balansingizga <b>{ref_bonus:,} so'm</b> bonus oling!\n\n"
        f"📊 <b>Sizning statistikangiz:</b>\n"
        f"• Taklif qilingan do'stlar: <b>{ref_count} ta</b>\n"
        f"• Ishlangan jami bonus: <b>{ref_count * ref_bonus:,} so'm</b>\n\n"
        f"🔗 <b>Sizning shaxsiy referal havolangiz:</b>\n"
        f"<code>{ref_link}</code>"
    )
    share_text = f"🚕 Eng tezkor va qulay taksi hamda pochta xizmati! Botga kiring: 👇\n{ref_link}"
    import urllib.parse
    encoded_share = urllib.parse.quote(share_text)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Do'stlarga ulashish (Share)", url=f"https://t.me/share/url?url={ref_link}&text={encoded_share}")],
        [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_profile")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.my_chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION), F.chat.type.in_(["group", "supergroup"]))
async def bot_added_to_group(event: ChatMemberUpdated):
    chat_info = event.chat
    bot_info = await event.bot.get_me()
    
    # Save to DB
    await add_group(chat_info.id, chat_info.title)
    
    text = get_trans('uz', 'bot_added_to_group').format(title=chat_info.title)
    try:
        await event.bot.send_message(chat_id=chat_info.id, text=text, parse_mode="HTML")
    except: pass


@router.my_chat_member(ChatMemberUpdatedFilter(LEAVE_TRANSITION), F.chat.type.in_(["group", "supergroup"]))
async def bot_left_group(event: ChatMemberUpdated):
    # If the bot is removed from a group, remove the group from DB
    if event.chat.type in ["group", "supergroup"]:
        await delete_group(event.chat.id)
    # If a user blocks the bot in private chat, remove them from bot_starters
    elif event.chat.type == "private":
        await remove_user_started(event.chat.id)


# --- 🎯 GROUP BUTTON REDIRECTS ---

@router.message(F.chat.type.in_(["group", "supergroup"]), F.text.in_({"👤 Yo'lovchi", "🚗 Haydovchi"}))
async def group_role_redirect(message: types.Message):
    bot_info = await message.bot.get_me()
    # Cooldown check to prevent flood in groups
    now = asyncio.get_event_loop().time()
    last_user_warn = USER_WARNING_COOLDOWN.get(message.from_user.id, 0)
    last_chat_warn = CHAT_WARNING_COOLDOWN.get(message.chat.id, 0)
    
    if (now - last_user_warn) < USER_WARNING_TIME:
        return
    if (now - last_chat_warn) < CHAT_WARNING_TIME:
        return
        
    import html
    safe_name = html.escape(message.from_user.full_name)
    
    text = (
        f"<b>👋 Xush kelibsiz, {safe_name}!</b>\n\n"
        f"Ro'yxatdan o'tish yoki xizmatlardan foydalanish uchun botning o'ziga kiring:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Botga o'tish", url=f"https://t.me/{bot_info.username}")]])
    
    try:
        await message.answer(text, reply_markup=types.ReplyKeyboardRemove(), parse_mode="HTML")
        USER_WARNING_COOLDOWN[message.from_user.id] = now
        CHAT_WARNING_COOLDOWN[message.chat.id] = now
    except: pass



@router.channel_post()
async def channel_message_reactor(message: types.Message):
    """Reacts to every post in channels."""
    try:
        await message.react([types.ReactionTypeEmoji(emoji="👍")])
    except Exception:
        pass



@router.message(F.chat.type == "private", IsMenuButton('charity_btn'))
async def show_charity_info(message: types.Message):
    lang = await get_user_language(message.from_user.id)
    card = await get_setting('charity_card', "O'rnatilmagan")
    
    # 1. Doimiy Ehson
    try:
        p_total = int(float(await get_setting('charity_p_total', '0')))
    except: p_total = 0
    p_info = await get_setting('charity_p_info', "Oylik xayriya yig'uvi.")
    
    text = f"<b>❤️ EHSON (XAYRIYA) BO'LIMI</b>\n━━━━━━━━━━━━━━\n"
    text += f"<b>📅 OYLIK EHSON (Doimiy)</b>\n"
    text += f"📝 {p_info}\n"
    text += f"📊 To'plandi: <b>{p_total:,} so'm</b>\n"
    text += f"<i>(Har oyning 1-sanasida yangilanadi)</i>\n\n"
    
    # 2. Maqsadli ehsonlar ro'yxati
    active_charities = await get_active_targeted_charities()
    if active_charities:
        text += f"<b>✨ MAQSADLI EHSONLAR:</b>\n"
        text += f"Quyidagilardan birini tanlab batafsil ma'lumot olishingiz mumkin:\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Doimiy ehson qilish", callback_data="charity_donate_p")]
    ])
    
    for c in active_charities:
        cid, title = c[0], c[1]
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🎁 {title}", callback_data=f"charity_view_{cid}")])
        
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 " + get_trans(lang, 'back'), callback_data="close_profile")])
    
    media_id = await get_setting('charity_media_id')
    if media_id:
        try:
            await message.answer_photo(media_id, caption=text, reply_markup=kb, parse_mode="HTML")
            return
        except: pass
            
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("charity_view_"))
async def view_charity_detail(callback: types.CallbackQuery):
    await callback.answer()
    cid = int(callback.data.replace("charity_view_", ""))
    c = await get_targeted_charity(cid)
    if not c: return
    
    # cid, title, desc, target, current, expiry, media_id, media_type...
    _, title, desc, target, current, expiry, media_id, m_type = c[:8]
    
    text = (
        f"<b>✨ {title}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"📝 {desc}\n\n"
        f"📊 <b>To'plandi:</b> <b>{int(current):,} / {int(target):,} so'm</b>\n"
        f"⏳ <b>Muddat:</b> <b>{expiry}</b> gacha\n"
        f"━━━━━━━━━━━━━━\n"
        f"💳 <b>Karta:</b> <code>{await get_setting('charity_card')}</code>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Balansdan ehson", callback_data=f"charity_donate_o_{cid}")],
        [InlineKeyboardButton(text="📸 Chek yuborish", callback_data=f"charity_receipt_{cid}")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="charity_btn")] # This is IsMenuButton but for query
    ])
    
    # Simple fix for back button in query
    kb.inline_keyboard[-1][0].callback_data = "back_to_charity_list"

    if media_id:
        if m_type == 'video':
            await callback.message.answer_video(media_id, caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await callback.message.answer_photo(media_id, caption=text, reply_markup=kb, parse_mode="HTML")
        await callback.message.delete()
    else:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "back_to_charity_list")
async def back_to_charity_list(callback: types.CallbackQuery):
    await callback.message.delete()
    await show_charity_info(callback.message)

@router.callback_query(F.data.startswith("charity_donate_"))
async def charity_donate_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split("_")
    dtype = parts[2] # 'p' or 'o'
    cid = parts[3] if len(parts) > 3 else None
    
    lang = await get_user_language(callback.from_user.id)
    user = await get_user(callback.from_user.id)
    balance = user[6] if user else 0
    
    await state.update_data(donate_type=dtype, donate_cid=cid)
    await state.set_state(PaymentStates.waiting_for_charity_amount)
    
    await callback.message.answer(
        get_trans(lang, 'charity_enter_amount').format(balance=balance), 
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_profile")]])
    )

@router.callback_query(F.data.startswith("charity_receipt_"))
async def charity_receipt_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    cid = int(callback.data.replace("charity_receipt_", ""))
    await state.update_data(receipt_cid=cid)
    await state.set_state(PaymentStates.waiting_for_charity_receipt) 
    
    await callback.message.answer(
        "<b>📸 CHEKNI YUBORING</b>\n━━━━━━━━━━━━━━\n"
        "Iltimos, to'lov qilingan chekning rasmini yuboring.\n"
        "Admin tasdiqlaganidan so'ng ehsoningiz hisobga olinadi.",
        parse_mode="HTML"
    )

@router.message(PaymentStates.waiting_for_charity_receipt, F.photo)
async def process_charity_receipt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid = data.get('receipt_cid')
    
    photo_id = message.photo[-1].file_id
    await add_charity_receipt(message.from_user.id, cid, 0, photo_id) 
    
    charity = await get_targeted_charity(cid)
    admin_text = (
        f"<b>🧾 YANGI EHSON CHEKI</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 <b>User:</b> {message.from_user.full_name}\n"
        f"🎁 <b>Ehson:</b> {charity[1]}\n\n"
        f"Iltimos, chekni tekshiring va summani kiriting."
    )
    
    await message.bot.send_photo(ADMIN_ID, photo_id, caption=admin_text, parse_mode="HTML")
    await message.answer("✅ <b>Chek adminga yuborildi!</b>\n\nTez orada ko'rib chiqiladi. Alloh rozi bo'lsin!")
    await state.clear()

@router.message(PaymentStates.waiting_for_charity_amount, F.text)
async def charity_donate_process(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)
    lang = user[8] if user else 'uz'
    balance = user[6] if user else 0
    
    amount_str = re.sub(r'[^\d]', '', message.text)
    if not amount_str or int(amount_str) <= 0:
        await message.answer("❌ Noto'g'ri summa kiritildi. Iltimos, faqat raqam yozing.")
        return
        
    amount = int(amount_str)
    if amount > balance:
        await message.answer(get_trans(lang, 'low_balance'))
        return
        
    try:
        data = await state.get_data()
        dtype = data.get('donate_type', 'p')
        setting_key = 'charity_p_total' if dtype == 'p' else 'charity_o_total'
        
        # Deduct from user
        await update_user_balance(user_id, -amount, f"Xayriya ({'Doimiy' if dtype == 'p' else 'Maqsadli'})", 'out')
        
        # Update global total
        try:
            current_total = int(float(await get_setting(setting_key, '0')))
        except:
            current_total = 0
        new_total = current_total + amount
        await update_setting(setting_key, str(new_total))
        
        # Record donation for thank you message later
        cid = data.get('donate_cid')
        await add_charity_donation(user_id, amount, dtype, cid)
        
        # Notify Admin
        admin_text = (
            f"❤️ <b>YANGI EHSON!</b> ({'Doimiy' if dtype == 'p' else 'Maqsadli'})\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 <b>Foydalanuvchi:</b> {message.from_user.full_name}\n"
            f"💰 <b>Summa:</b> <b>{amount:,} so'm</b>\n"
            f"📊 <b>Yangi total:</b> <b>{new_total:,} so'm</b>"
        )
        try:
            await message.bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")
        except: pass
        
        await state.clear()
        await message.answer(get_trans(lang, 'charity_success').format(amount=amount), parse_mode="HTML")
        await show_charity_info(message)
        
    except ValueError:
        await message.answer(get_trans(lang, 'low_balance'))
    except Exception as e:
        logger.error(f"Charity Error: {e}")
        await message.answer("❌ Xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")

# --- 🎤 VOICE PROXY (Communication) ---

@router.message(F.chat.type == "private", F.voice)
async def voice_proxy_handler(message: types.Message):
    user_id = message.from_user.id
    peer_id = await get_active_order_peer(user_id)
    
    if not peer_id:
        return # Fall through to other routers (voice.py)
    
    lang = await get_user_language(peer_id)

    caption_map = {
        'uz': "🎤 <b>Safar hamrohingizdan ovozli xabar:</b>",
        'ru': "🎤 <b>Голосовое сообщение от вашего спутника:</b>",
        'en': "🎤 <b>Voice message from your companion:</b>"
    }
    caption = caption_map.get(lang, caption_map['uz'])
    
    try:
        await message.bot.send_voice(
            chat_id=peer_id,
            voice=message.voice.file_id,
            caption=caption,
            parse_mode="HTML"
        )
        await message.answer("✅ Yuborildi.")
    except Exception as e:
        logger.error(f"Voice Proxy Error: {e}")

@router.message(F.chat.type.in_(["group", "supergroup"]), Command("start"))
async def group_start_handler(message: types.Message):
    bot_info = await message.bot.get_me()
    text = (
        "<b>🚕 CHIROQCHI TAKSI — Rasmiy yordamchi</b>\n"
        "━━━━━━━━━━━━━━\n"
        "🤖 Ushbu guruhda bot quyidagi vazifalarni bajaradi:\n\n"
        "🛡 <b>Obuna nazorati:</b> Faqat a'zolar yozishini ta'minlaydi.\n\n"
        "📌 <b>Guruh buyruqlari:</b>\n"
        "• /start — Ishni boshlash\n"
        "• /info — Bot haqida ma'lumot\n"
        "• /bot — Obuna sozlamalari\n"
        "━━━━━━━━━━━━━━\n"
        "💡 <b>Xizmatlardan to'liq foydalanish uchun botga o'ting!</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Botni ishga tushirish", url=f"https://t.me/{bot_info.username}?start=group")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(F.chat.type.in_(["group", "supergroup"]), Command("info"))
async def group_cmd_info(message: types.Message):
    """Guruh uchun /info: Bot haqida ma'lumot"""
    bot_info = await message.bot.get_me()
    text = get_trans('uz', 'group_info_text')
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Botni ochish", url=f"https://t.me/{bot_info.username}")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(F.chat.type.in_(["group", "supergroup"]), Command("bot"))
async def group_cmd_bot(message: types.Message):
    """Guruh uchun /bot: Admin tomonidan boshqarish"""
    user_id = message.from_user.id
    bot_info = await message.bot.get_me()

    # Faqat guruh admin yoki bot admin
    is_bot_admin = (user_id == ADMIN_ID)
    try:
        member = await message.bot.get_chat_member(message.chat.id, user_id)
        is_group_admin = member.status in ["administrator", "creator"]
    except Exception:
        is_group_admin = False
        
    # Shuningdek yashirin admin bo'lsa (anonim tarzda yozsa)
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        is_group_admin = True

    if not (is_bot_admin or is_group_admin):
        try:
            try:
                await message.delete()
            except:
                pass
        except Exception:
            pass
        warn = await message.answer("⛔ Bu buyruq faqat guruh adminlari uchun!")
        import asyncio
        async def _del():
            await asyncio.sleep(10)
            try: await warn.delete()
            except: pass
        asyncio.create_task(_del())
        return

    # Admin uchun guruh sozlamalari
    args = message.text.split()
    if len(args) > 1 and args[1].lower() in ["on", "off"]:
        if args[1].lower() == "off":
            await toggle_group_guard(message.chat.id, 0)
            await message.answer("🛑 <b>Obuna nazorati o'chirildi.</b>\nEndi hamma yozishi mumkin.", parse_mode="HTML")
        else:
            await toggle_group_guard(message.chat.id, 1)
            await message.answer(f"✅ <b>Obuna nazorati yoqildi!</b>\n\nEndi faqat @{bot_info.username} botimizga obuna bo'lganlar guruhda yoza oladi.", parse_mode="HTML")
        return

    guard_on = await is_group_guarded(message.chat.id)
    status_icon = "✅ Yoqilgan" if guard_on else "❌ O'chirilgan"

    text = (
        f"🤖 <b>BOT SOZLAMALARI</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"💬 Guruh: <b>{message.chat.title}</b>\n"
        f"🛡 Obuna nazorati: <b>{status_icon}</b>\n\n"
        f"Quyidagi tugmalar orqali sozlang, yoki:\n"
        f"<code>/bot on</code> - Yoqish\n"
        f"<code>/bot off</code> - O'chirish"
    )
    action_text = "O'chirish" if guard_on else "Yoqish"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🛡 Obuna nazoratini {action_text}",
            callback_data=f"toggle_guard_{message.chat.id}"
        )],
        [InlineKeyboardButton(text="📊 Guruh statistikasi", callback_data=f"group_stats_{message.chat.id}")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_profile")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("toggle_guard_"))
async def toggle_guard_callback(callback: types.CallbackQuery):
    chat_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    # Faqat admin
    is_bot_admin = (user_id == ADMIN_ID)
    try:
        member = await callback.bot.get_chat_member(chat_id, user_id)
        is_group_admin = member.status in ["administrator", "creator"]
    except Exception:
        is_group_admin = False

    if not (is_bot_admin or is_group_admin):
        return await callback.answer("⛔ Ruxsat yo'q!", show_alert=True)

    # Get current state to toggle
    current = await is_group_guarded(chat_id)
    new_status = 0 if current else 1
    new_state = await toggle_group_guard(chat_id, new_status)
    status = "✅ Yoqildi" if new_state else "❌ O'chirildi"
    await callback.answer(f"Obuna nazorati: {status}", show_alert=True)
    
    guard_on = new_state
    status_icon = "✅ Yoqilgan" if guard_on else "❌ O'chirilgan"
    
    title = callback.message.chat.title if callback.message.chat else "Guruh"
    text = (
        f"🤖 <b>BOT SOZLAMALARI</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"💬 Guruh: <b>{title}</b>\n"
        f"🛡 Obuna nazorati: <b>{status_icon}</b>\n\n"
        f"Quyidagi tugmalar orqali sozlang, yoki:\n"
        f"<code>/bot on</code> - Yoqish\n"
        f"<code>/bot off</code> - O'chirish"
    )
    action_text = "O'chirish" if guard_on else "Yoqish"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🛡 Obuna nazoratini {action_text}",
            callback_data=f"toggle_guard_{chat_id}"
        )],
        [InlineKeyboardButton(text="📊 Guruh statistikasi", callback_data=f"group_stats_{chat_id}")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_profile")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data.startswith("group_stats_"))
async def group_stats_callback(callback: types.CallbackQuery):
    chat_id = int(callback.data.split("_")[2])
    try:
        count = (await callback.bot.get_chat_member_count(chat_id))
        await callback.answer(f"👥 A'zolar soni: {count} ta", show_alert=True)
    except Exception:
        await callback.answer("❌ Ma'lumot olishda xatolik.", show_alert=True)



@router.message(F.chat.type == "private", Command("help"))
async def cmd_help(message: types.Message):
    lang = await get_user_language(message.from_user.id)
    text = (
        "<b>📖 AQLLI YORDAM TIZIMI</b>\n"
        "━━━━━━━━━━━━━━\n"
        "Sizga qanday yordam bera olaman? Kerakli bo'limni tanlang:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚕 Taksi chaqirish", callback_data="help_taxi"), InlineKeyboardButton(text="📦 Pochta", callback_data="help_parcel")],
        [InlineKeyboardButton(text="💰 Pul ishlash", callback_data="help_earn"), InlineKeyboardButton(text="💳 Hamyon", callback_data="help_wallet")],
        [InlineKeyboardButton(text="🛡 Xavfsizlik", callback_data="help_safety"), InlineKeyboardButton(text="👨‍💻 Admin", callback_data="help_admin")],
        [InlineKeyboardButton(text="🔙 Yopish", callback_data="close_profile")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("help_"))
async def help_callback_handler(callback: types.CallbackQuery):
    await callback.answer()
    lang = await get_user_language(callback.from_user.id)

    # "Ortga" tugmasi bosilganda — asosiy yordam menyusiga qaytish
    if callback.data == "help_main":
        main_text = (
            "<b>📖 AQLLI YORDAM TIZIMI</b>\n"
            "━━━━━━━━━━━━━━\n"
            "Sizga qanday yordam bera olaman? Kerakli bo'limni tanlang:"
        )
        main_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚕 Taksi chaqirish", callback_data="help_taxi"),
             InlineKeyboardButton(text="📦 Pochta", callback_data="help_parcel")],
            [InlineKeyboardButton(text="💰 Pul ishlash", callback_data="help_earn"),
             InlineKeyboardButton(text="💳 Hamyon", callback_data="help_wallet")],
            [InlineKeyboardButton(text="🛡 Xavfsizlik", callback_data="help_safety"),
             InlineKeyboardButton(text="👨‍💻 Admin", callback_data="help_admin")],
            [InlineKeyboardButton(text="🔙 Yopish", callback_data="close_profile")]
        ])
        try:
            await callback.message.edit_text(main_text, reply_markup=main_kb, parse_mode="HTML")
        except:
            pass
        return

    key = callback.data.split("_")[1]
    help_texts = {
        'taxi':   get_trans(lang, 'help_taxi'),
        'parcel': get_trans(lang, 'help_parcel'),
        'earn':   get_trans(lang, 'help_earn'),
        'wallet': get_trans(lang, 'help_wallet'),
        'safety': get_trans(lang, 'help_safety'),
        'admin':  get_trans(lang, 'help_admin').format(admin_id=ADMIN_ID),
    }

    text = help_texts.get(key)
    if not text:
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="help_main")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        pass

# --- 🎁 BONUSES & PROMOS ---

@router.message(F.chat.type == "private", IsMenuButton('daily_bonus_btn'))
async def claim_bonus(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    
    # Get bonus amount from settings or default 200
    bonus_amount = int(await get_setting('daily_bonus_amount', '200'))
    
    amount, status = await check_claim_daily_bonus(user_id, bonus_amount)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_profile")]])
    if status == 'success':
        await message.answer(get_trans(lang, 'daily_bonus_success').format(amount=amount), reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(get_trans(lang, 'daily_bonus_error'), reply_markup=kb, parse_mode="HTML")

@router.message(F.chat.type == "private", IsMenuButton('promo_btn'))
async def promo_prompt(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    await state.set_state(PaymentStates.waiting_for_promo)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_profile")]])
    await message.answer(get_trans(lang, 'promo_title'), reply_markup=kb, parse_mode="HTML")

@router.message(PaymentStates.waiting_for_promo, F.text)
async def redeem_promo(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    code = message.text.upper().strip()
    
    amount, status = await validate_and_use_promocode(user_id, code)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_profile")]])
    if status == 'success':
        await message.answer(get_trans(lang, 'promo_success').format(amount=amount), reply_markup=kb, parse_mode="HTML")
        await state.clear()
    elif status == 'limit_reached':
        await message.answer(get_trans(lang, 'promo_error_limit'), reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(get_trans(lang, 'promo_error_not_found'), reply_markup=kb, parse_mode="HTML")

# --- 🚨 SOS ALERT ---

@router.callback_query(F.data == "sos_alert")
async def sos_trigger(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    lang = user[8] if user else 'uz'
    
    await state.set_state(Emergency.waiting_for_location)
    
    # Request location
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📍 " + get_trans(lang, 'share_live_location'), request_location=True)],
        [KeyboardButton(text=get_trans(lang, 'cancel'))]
    ], resize_keyboard=True)
    
    await callback.message.answer(
        "🚨 <b>SOS REJIMI YOQILDI!</b>\n\n"
        "Iltimos, zudlik bilan lokatsiyangizni yuboring, biz uni adminga yetkazamiz:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(Emergency.waiting_for_location, F.location)
async def process_sos_location(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)
    lang = user[8] if user else 'uz'
    
    import html
    safe_name = html.escape(message.from_user.full_name)
    
    caption = get_trans('uz', 'sos_alert').format(
        name=safe_name,
        phone=user[2] if user else "Noma'lum",
        user_id=user_id
    )
    
    # Send location to Admin
    await message.bot.send_location(
        chat_id=ADMIN_ID,
        latitude=message.location.latitude,
        longitude=message.location.longitude
    )
    await message.bot.send_message(ADMIN_ID, f"🚨 <b>SOS LOKATSIYASI:</b>\n\n{caption}", parse_mode="HTML")
    
    await state.clear()
    
    role = user[4] if user else 'passenger'
    if role == 'passenger':
        menu = await get_passenger_menu(is_admin=(user_id == ADMIN_ID), lang=lang)
    else:
        dr = await get_driver(user_id)
        menu = await get_driver_menu(is_online=dr[6] if dr else False, is_admin=(user_id == ADMIN_ID), lang=lang)
        
    await message.answer(
        "✅ <b>Lokatsiyangiz adminga yuborildi!</b>\n\nTez orada siz bilan bog'lanishadi.",
        reply_markup=menu,
        parse_mode="HTML"
    )

@router.message(Emergency.waiting_for_location, F.text)
async def cancel_sos(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    if message.text == get_trans(lang, 'cancel'):
        await state.clear()
        user = await get_user(message.from_user.id)
        role = user[4] if user else 'passenger'
        if role == 'passenger':
            menu = await get_passenger_menu(is_admin=(message.from_user.id == ADMIN_ID), lang=lang)
        else:
            dr = await get_driver(message.from_user.id)
            menu = await get_driver_menu(is_online=dr[6] if dr else False, is_admin=(message.from_user.id == ADMIN_ID), lang=lang)
            
        await message.answer("❌ SOS bekor qilindi.", reply_markup=menu)
    else:
        # Boshqa matn kiritilsa ham stateni tozalaymiz
        await state.clear()
        await message.answer("❌ SOS bekor qilindi.", reply_markup=types.ReplyKeyboardRemove())

@router.message(F.chat.type == "private", IsMenuButton('manual'))
async def show_manual_handler(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    if not user: return
    
    lang = user[8]
    role = user[4]
    
    if role == 'passenger':
        text = get_trans(lang, 'manual_p_text')
        video_url = await get_setting('manual_video_passenger', 'https://youtube.com')
    else:
        text = get_trans(lang, 'manual_d_text')
        video_url = await get_setting('manual_video_driver', 'https://youtube.com')
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📺 Videoni ko'rish", url=video_url)],
        [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_profile")]
    ])
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- 🛒 ORDER ACTIONS (Shared for Taxi & Parcel) ---

@router.callback_query(F.data.startswith("raise_price_"))
async def prompt_new_price(callback: types.CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[2])
    await state.update_data(current_order_id=order_id)
    lang = await get_user_language(callback.from_user.id)
    
    order = await get_order(order_id)
    if order and order[13] == 'parcel':
        await state.set_state(ParcelProcess.updating_price)
    else:
        await state.set_state(OrderProcess.updating_price)
        
    await callback.message.answer("💰 <b>Yangi narx:</b>", parse_mode="HTML")
    await callback.answer()

@router.message(OrderProcess.updating_price, F.text)
@router.message(ParcelProcess.updating_price, F.text)
async def process_price_update(message: types.Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get('current_order_id')
    lang = await get_user_language(message.from_user.id)
    if not order_id:
        await message.answer("❌ Xatolik: Buyurtma topilmadi.")
        return await state.clear()

    try:
        new_price = float(message.text.replace(" ", "").replace(",", ""))
        min_price = float(await get_setting('min_price', '5000'))
        if new_price < min_price:
            return await message.answer(f"❌ Minimal narx: {int(min_price):,} so'm")
            
        await update_order_price(order_id, new_price)
        
        # Notify user
        await message.answer(f"✅ Narx muvaffaqiyatli yangilandi: <b>{int(new_price):,} so'm</b>.\nHaydovchilarga qayta yuborildi.", parse_mode="HTML")
        
        # Re-broadcast with new price
        order = await get_order(order_id)
        if order:
            from handlers.driver import broadcast_order
            asyncio.create_task(broadcast_order(
                bot=message.bot, 
                order_id=order_id, 
                from_loc=order[3], 
                to_loc=order[4], 
                price=new_price, 
                passenger_count=order[6], 
                scheduled_time=order[7] or "Hozir", 
                from_lat=order[9], 
                from_lon=order[10], 
                car_class=order[12],
                parcel_photo=order[14],
                order_type=order[13]
            ))
        await state.clear()
    except Exception as e:
        logger.error(f"Price update error: {e}")
        await message.answer("❌ Xato! Faqat raqam kiriting (masalan: 50000).")

@router.message(F.text.in_({"❌ Buyurtmani bekor qilish", "❌ Отменить заказ", "❌ Cancel Order"}))
async def cancel_active_order(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    orders = await get_passenger_active_orders(message.from_user.id)
    
    if not orders:
        is_admin = message.from_user.id == ADMIN_ID
        await message.answer(get_trans(lang, 'no_active_orders'), reply_markup=await get_passenger_menu(is_admin=is_admin, lang=lang))
        return await state.clear()
        
    for order in orders:
        order_id = order[0]
        await update_order_status(order_id, 'cancelled')
        
        # Notify driver if accepted
        if order[2]: # driver_id
            try:
                await message.bot.send_message(order[2], f"⚠️ Buyurtma yo'lovchi tomonidan bekor qilindi.")
            except: pass
            
    is_admin = message.from_user.id == ADMIN_ID
    await message.answer("❌ Buyurtma bekor qilindi.", reply_markup=await get_passenger_menu(is_admin=is_admin, lang=lang))
    await state.clear()

@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    order_id = int(callback.data.split("_")[2])
    lang = await get_user_language(callback.from_user.id)
    
    order = await get_order(order_id)
    if not order: return
    
    await update_order_status(order_id, 'cancelled')
    
    if order[2]: # driver_id
        try:
            await callback.bot.send_message(order[2], f"⚠️ Buyurtma yo'lovchi tomonidan bekor qilindi.")
        except: pass
        
    await callback.message.edit_text("❌ Buyurtma bekor qilindi.")
    await state.clear()
# --- 🛠 GLOBAL NO-OP FOR DEAD BUTTONS ---
@router.callback_query(F.data.in_({"none", "noop", "noop_alert", "close_profile"}))
async def global_noop_handler(callback: types.CallbackQuery):
    """Handles buttons that are meant to be purely decorative or need simple closing."""
    if callback.data == "close_profile":
        try:
            try:
                await callback.message.delete()
            except:
                pass
        except:
            pass
    elif callback.data == "noop_alert":
        await callback.answer("Hozircha bu bo'lim faol emas.", show_alert=True)
    else:
        await callback.answer()

# ─── UNIVERSAL AUTO-INTELLIGENCE RESPONDER ────────────────────────────────

INTENT_KEYWORDS = {
    'greeting': [
        'salom', 'assalomu', 'alaykum', 'privet', 'zdravstvuyte', 'hello', 'hi',
        'qandaysiz', 'yaxshimisiz', 'charchamang', 'qalesiz', 'sallom', 'valaykum'
    ],
    'price': [
        'narx', 'narxi', 'qancha', 'necha pul', 'nechi pul', 'skolko', 'stoit',
        'toshkentga narx', 'yo\'lkira', 'yolkira', 'tarif', 'qanchadan'
    ],
    'driver': [
        'haydovchi', 'taksist', 'ishlash', 'qanday ulanish', 'mashinam bor',
        'ish bor', 'ulanish', 'voditel', 'rabota', 'ro\'yxatdan o\'tish haydovchi'
    ],
    'support': [
        'admin', 'telefon', 'bog\'lanish', 'boglanish', 'aloqa', 'yordam',
        'kontakt', 'nomer', 'admin kim', 'podderjka', 'support', 'muammo'
    ],
    'wallet': [
        'balans', 'hamyon', 'payme', 'click', 'pul solish', 'to\'lov',
        'hisob', 'hisobim', 'koshelek', 'popolnit'
    ],
    'parcel': [
        'pochta', 'posilka', 'yuk', 'dastavka', 'dostavka', 'bervorgan',
        'posilka narxi', 'bervorish', 'paket'
    ]
}

@router.message(F.chat.type == "private")
async def universal_smart_fallback_handler(message: types.Message, state: FSMContext):
    """
    Universal Intelligent Message Analyzer:
    Analyzes any incoming message, identifies user intent, and provides instant smart replies or AI answers.
    """
    # If user is in an active FSM state, do not intercept
    curr_state = await state.get_state()
    if curr_state is not None:
        return

    lang = await get_user_language(message.from_user.id)
    text = (message.text or message.caption or "").strip()
    t_lower = text.lower()
    
    if not text:
        return

    bot_info = await message.bot.get_me()

    # 1. Check Greetings
    if any(w in t_lower for w in INTENT_KEYWORDS['greeting']) and len(text.split()) <= 4:
        greeting_text = (
            f"👋 <b>Assalomu alaykum, {message.from_user.first_name}!</b>\n\n"
            f"Men <b>Chiroqchi Taksi & Pochta</b> platformasining aqlli yordamchisiman 🤖\n\n"
            f"Sizga qanday yordam bera olaman? Quyidagi xizmatlardan birini tanlang yoki to'g'ridan-to'g'ri boradigan manzilingizni yozing (masalan: <i>\"Toshkentga 2 kishi\"</i>):"
        ) if lang == 'uz' else (
            f"👋 <b>Здравствуйте, {message.from_user.first_name}!</b>\n\n"
            f"Я умный помощник службы <b>Чиракчи Такси и Почта</b> 🤖\n\n"
            f"Чем могу помочь? Выберите нужный раздел или просто напишите куда вам нужно (например: <i>\"В Ташкент 2 человека\"</i>):"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🚕 Taksi chaqirish", callback_data="btn_quick_taxi"),
                InlineKeyboardButton(text="📦 Pochta yuborish", callback_data="btn_quick_parcel")
            ],
            [
                InlineKeyboardButton(text="💳 Hamyon", callback_data="btn_quick_wallet"),
                InlineKeyboardButton(text="👨‍💻 Adminga yozish", url="https://t.me/Admeral2002")
            ]
        ])
        return await message.answer(greeting_text, reply_markup=kb, parse_mode="HTML")

    # 2. Check Price inquiries
    if any(w in t_lower for w in INTENT_KEYWORDS['price']):
        price_text = (
            "💰 <b>NARXLAR VA TARIFLAR:</b>\n━━━━━━━━━━━━━━\n\n"
            "• <b>Chiroqchi ➔ Toshkent:</b> o'rtacha <b>100,000 – 140,000 so'm</b> / kishi\n"
            "• <b>Chiroqchi ➔ Samarqand:</b> o'rtacha <b>40,000 – 60,000 so'm</b> / kishi\n"
            "• <b>Chiroqchi ➔ Shahrisabz:</b> o'rtacha <b>25,000 – 35,000 so'm</b> / kishi\n"
            "• <b>Chiroqchi ➔ Qarshi:</b> o'rtacha <b>30,000 – 45,000 so'm</b> / kishi\n"
            "• <b>Pochta / Posilkalar:</b> <b>30,000 – 80,000 so'm</b> (hajmiga qarab)\n\n"
            "<i>💡 Shuningdek, siz o'zingiz xohlagan narxni taklif qilib buyurtma berishingiz mumkin!</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Hozir buyurtma berish", callback_data="btn_quick_taxi")],
            [InlineKeyboardButton(text="📦 Pochta yuborish", callback_data="btn_quick_parcel")]
        ])
        return await message.answer(price_text, reply_markup=kb, parse_mode="HTML")

    # 3. Check Driver registration inquiries
    if any(w in t_lower for w in INTENT_KEYWORDS['driver']):
        driver_text = (
            "🚗 <b>HAYDOVCHI SIFATIDA ULASHISH:</b>\n━━━━━━━━━━━━━━\n\n"
            "Platformamizda haydovchi bo'lib ishlash juda oson va daromadli!\n\n"
            "✅ Erkin grafik — xohlagan vaqtingizda ishlang;\n"
            "✅ Doimiy yo'lovchilar va pochtalar oqimi;\n"
            "✅ Birinchi 3 kunlik sinov muddati MUTLAQO BEPUL!\n\n"
            "Boshlash uchun quyidagi tugmani bosing va mashina ma'lumotlaringizni kiriting:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚕 Haydovchi bo'lib ro'yxatdan o'tish", callback_data="role_switch_driver")]
        ])
        return await message.answer(driver_text, reply_markup=kb, parse_mode="HTML")

    # 4. Check Support / Admin inquiries
    if any(w in t_lower for w in INTENT_KEYWORDS['support']):
        support_text = (
            "👨‍💻 <b>ADMINISTRATSIYA VA YORDAM:</b>\n━━━━━━━━━━━━━━\n\n"
            "Savol, taklif yoki muammolar bo'yicha biz bilan bog'laning:\n\n"
            "👤 <b>Bosh Admin:</b> @Admeral2002\n"
            "⏰ <b>Ish vaqti:</b> 24/7 (Doimiy aloqadamiz)\n\n"
            "Quyidagi tugma orqali to'g'ridan-to'g'ri adminga yozishingiz mumkin:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Adminga yozish (Telegram)", url="https://t.me/Admeral2002")]
        ])
        return await message.answer(support_text, reply_markup=kb, parse_mode="HTML")

    # 5. Check Wallet / Payment inquiries
    if any(w in t_lower for w in INTENT_KEYWORDS['wallet']):
        wallet_text = (
            "💳 <b>HAMYON VA TO'LOVLAR:</b>\n━━━━━━━━━━━━━━\n\n"
            "Hisobingizni Click, Payme yoki karta orqali 24/7 tezkor to'ldirishingiz mumkin.\n\n"
            "Hamyon bo'limiga o'tish uchun quyidagi tugmani bosing:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Hamyonni ochish", callback_data="btn_quick_wallet")]
        ])
        return await message.answer(wallet_text, reply_markup=kb, parse_mode="HTML")

    # 6. Check Parcel inquiries
    if any(w in t_lower for w in INTENT_KEYWORDS['parcel']):
        parcel_text = (
            "📦 <b>POCHTA VA YUK YETKAZISH XIZMATI:</b>\n━━━━━━━━━━━━━━\n\n"
            "Xat, hujjat, quti, dori-darmon va har qanday posilkalarni viloyatlararo ishonchli yetkazib beramiz.\n\n"
            "Pochta yuborish uchun quyidagi tugmani bosing:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 Pochta buyurtmasi berish", callback_data="btn_quick_parcel")]
        ])
        return await message.answer(parcel_text, reply_markup=kb, parse_mode="HTML")

    # 7. Universal AI Assistant (Gemini 2.0 AI) for all other general questions/conversations
    from utils.ai_helper import get_ai_response
    waiting_msg = None
    try:
        waiting_msg = await message.answer("🤖 <i>O'ylanmoqda...</i>", parse_mode="HTML")
        ai_resp, _ = await get_ai_response(text, [], user_lang=lang)
        if waiting_msg:
            await waiting_msg.delete()

        if ai_resp:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🚕 Taksi chaqirish", callback_data="btn_quick_taxi"),
                    InlineKeyboardButton(text="📦 Pochta yuborish", callback_data="btn_quick_parcel")
                ]
            ])
            return await message.answer(f"🤖 <b>AI Yordamchi:</b>\n\n{ai_resp}", reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        if waiting_msg:
            try: await waiting_msg.delete()
            except: pass
        logger.error(f"Universal AI fallback error: {e}")

    # 8. Friendly Fallback Menu Prompt
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚕 Taksi chaqirish", callback_data="btn_quick_taxi"),
            InlineKeyboardButton(text="📦 Pochta yuborish", callback_data="btn_quick_parcel")
        ],
        [InlineKeyboardButton(text="👨‍💻 Adminga yozish", url="https://t.me/Admeral2002")]
    ])
    await message.answer(
        "💡 <i>Sizga qanday yordam bera olaman? Xizmatni tanlang yoki buyurtmangizni yozing (masalan: \"Toshkentga 2 kishi\"):</i>",
        reply_markup=kb,
        parse_mode="HTML"
    )


# ── Quick Action Callback Routers ──────────────────────────────────────────

@router.callback_query(F.data == "btn_quick_taxi")
async def quick_taxi_callback(callback: types.CallbackQuery, state: FSMContext):
    from handlers.passenger import start_order
    await callback.message.delete()
    await start_order(callback.message, state, user_id=callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "btn_quick_parcel")
async def quick_parcel_callback(callback: types.CallbackQuery, state: FSMContext):
    from handlers.parcel import start_parcel_order
    await callback.message.delete()
    await start_parcel_order(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "btn_quick_wallet")
async def quick_wallet_callback(callback: types.CallbackQuery, state: FSMContext):
    from handlers.wallet import wallet_menu
    await callback.message.delete()
    await wallet_menu(callback.message, state)
    await callback.answer()


