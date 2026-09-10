from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from database.db import (
    get_referral_list, get_driver_sub_status, get_pending_withdrawals, get_withdrawal_request,
    update_withdrawal_status, add_withdrawal_request, extend_driver_subscription,
    add_driver_quota, update_user_balance_conn, purchase_priority, is_priority_driver,
    get_user, get_setting, get_referral_stats, get_driver_earnings_stats,
    update_user_balance, get_user_language, add_deposit
)
from utils.formatters import format_currency
from utils.locales import get_trans
from utils.states import PaymentStates
from utils.utils import IsMenuButton
from config import ADMIN_ID
import os
import uuid
from datetime import datetime
from utils.ocr_helper import extract_receipt_amount
import urllib.parse
from aiogram.types import FSInputFile
import logging

logger = logging.getLogger(__name__)

router = Router()

@router.message(IsMenuButton('wallet'))
@router.message(IsMenuButton('driver_stats'))
async def show_wallet(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    if not user:
        return
    
    # user indices: 0:id, 1:fullname, 2:phone, 3:seconary, 4:role, 5:status, 6:balance, 7:ref_by, 8:lang
    balance = user[6]
    lang = user[8]
    ref_count = await get_referral_stats(user_id)
    
    # Get settings for bonus info
    ref_bonus_amount = int(await get_setting('ref_bonus', '500'))
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    
    # Get stats for drivers
    is_driver = user[4] == 'driver'
    earnings_text = ""
    if is_driver:
        stats = await get_driver_earnings_stats(user_id)
        comm_val = stats.get('commission', 0)
        earnings_text = (
            f"{get_trans(lang, 'wallet_stats_title')}\n"
            f"{get_trans(lang, 'wallet_stats_today').format(amount=stats['today'])}\n"
            f"{get_trans(lang, 'wallet_stats_total').format(amount=stats['total'])}\n"
            f"{get_trans(lang, 'wallet_stats_commission').format(amount=comm_val)}\n"
        )
    
    text = get_trans(lang, 'wallet_info').format(
        balance=balance,
        cashback=0, 
        ref_bonus=ref_count * ref_bonus_amount
    )
    
    text += earnings_text
    
    text += f"\n\n👥 <b>Referallar:</b>\n"
    text += f"• Umumiy: {ref_count} ta do'st\n"
    text += f"• Daromad: {ref_count * ref_bonus_amount:,} so'm\n"
    text += f"🔗 <code>{ref_link}</code>"
    
    # Build keyboard — add tariff button for drivers
    buttons = [
        [InlineKeyboardButton(text=get_trans(lang, 'top_up_balance'), callback_data="top_up_balance")],
        [InlineKeyboardButton(text="👥 Taklif qilinganlar", callback_data="ref_list")],
    ]
    if is_driver:
        buttons.append([InlineKeyboardButton(text="📋 Tariflar & Obuna", callback_data="driver_tariffs")])
        if balance >= 50000:
            buttons.append([InlineKeyboardButton(text="💸 Pul yechib olish", callback_data="withdraw_request")])
    buttons.append([InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_wallet")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "ref_list")
async def show_referral_list_handler(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    user = await get_user(user_id)
    lang = user[8] if user else 'uz'
    referrals = await get_referral_list(user_id)
    
    if not referrals:
        return await callback.answer("Hozircha referallar yo'q.", show_alert=True)
        
    text = "<b>👥 TAKLIF QILINGAN DO'STLAR</b>\n\n"
    for ref in referrals[:20]: # Show last 20
        ref_id, name, phone, role, reg_date = ref
        role_icon = "👤" if role == 'passenger' else "🚕"
        text += f"{role_icon} <b>{name}</b> ({reg_date})\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="driver_tariffs" if (await get_user(user_id))[4] == 'driver' else "close_wallet")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    # Note: callback.answer() already called at line 92 - removed duplicate

@router.callback_query(F.data == "top_up_balance")
async def top_up_options(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    lang = user[8] if user else 'uz'
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Avtomatik (Payme/Click/Uzum)", callback_data="auto_top_up")],
        [InlineKeyboardButton(text="📸 Chek yuborish (Admin orqali)", callback_data="manual_top_up")],
        [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_wallet")]
    ])
    
    await callback.message.edit_text(
        "<b>💰 HISOBNI TO'LDIRISH</b>\n━━━━━━━━━━━━━━\n\nQaysi usulda to'lov qilmoqchisiz?",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "auto_top_up")
async def auto_top_up_amount(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PaymentStates.waiting_for_amount)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="10,000", callback_data="auto_pay_10000"), InlineKeyboardButton(text="20,000", callback_data="auto_pay_20000")],
        [InlineKeyboardButton(text="50,000", callback_data="auto_pay_50000"), InlineKeyboardButton(text="100,000", callback_data="auto_pay_100000")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="top_up_balance")]
    ])
    
    await callback.message.edit_text(
        "<b>💳 AVTOMATIK TO'LOV</b>\n━━━━━━━━━━━━━━\n\nQancha mablag' kiritmoqchisiz? Tayyor summalardan birini tanlang yoki o'zingiz raqam orqali kiriting (masalan: 15000):",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("auto_pay_"))
async def process_auto_pay_button(callback: types.CallbackQuery):
    amount = int(callback.data.replace("auto_pay_", ""))
    await send_invoice(callback.message, callback.from_user.id, amount)
    await callback.answer()

@router.message(PaymentStates.waiting_for_amount, F.text)
async def process_auto_pay_text(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.replace(" ", ""))
        if amount < 5000:
            return await message.answer("❌ Minimal to'lov summasi 5,000 so'm.")
        await state.clear()
        await send_invoice(message, message.from_user.id, amount)
    except:
        await message.answer("❌ Iltimos, faqat raqam kiriting (masalan: 10000)")

async def send_invoice(message: types.Message, user_id: int, amount: int):
    from config import PAYMENT_PROVIDER_TOKEN
    from aiogram.types import LabeledPrice
    
    if not PAYMENT_PROVIDER_TOKEN:
        return await message.answer("⚠️ Hozircha avtomatik to'lovlar ishlamayapti. Iltimos, 'Chek yuborish' usulidan foydalaning.")
        
    prices = [LabeledPrice(label=f"Hisob to'ldirish", amount=amount * 100)] # amount in tiyin
    
    await message.bot.send_invoice(
        chat_id=user_id,
        title="💰 Hisob to'ldirish",
        description=f"Botdagi hisobingizni {amount:,} so'mga to'ldirish.",
        payload=f"topup_{user_id}_{amount}",
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency="UZS",
        prices=prices,
        start_parameter="topup"
    )

@router.pre_checkout_query()
async def pre_checkout_query(pre_checkout_q: types.PreCheckoutQuery):
    await pre_checkout_q.bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: types.Message):
    amount = message.successful_payment.total_amount // 100
    user_id = message.from_user.id
    
    # Update balance
    await update_user_balance(user_id, amount, f"Payme/Click orqali to'lov", 'in')
    
    lang = await get_user_language(user_id)
    await message.answer(
        f"✅ <b>To'lov muvaffaqiyatli amalga oshirildi!</b>\n"
        f"Hisobingizga {amount:,} so'm tushdi.",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "manual_top_up")
async def manual_top_up_start(callback: types.CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    lang = user[8] if user else 'uz'
    card = await get_setting('admin_card', "O'rnatilmagan")
    
    await state.set_state(PaymentStates.waiting_for_receipt)
    try:
        await callback.message.edit_text(
            get_trans(lang, 'send_receipt_instr').format(card=card),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="top_up_balance")]
            ]),
            parse_mode="HTML"
        )
    except: pass
    await callback.answer()

@router.message(PaymentStates.waiting_for_receipt, F.photo)
async def process_receipt(message: types.Message, state: FSMContext):
    # To prevent flood, we check if state is already being cleared
    curr_state = await state.get_state()
    if not curr_state: return
    await state.clear() # Clear immediately
    
    user_id = message.from_user.id
    user = await get_user(user_id)
    lang = user[8] if user else 'uz'
    
    photo_id = message.photo[-1].file_id
    
    # OCR: Try to detect amount
    await message.answer("⏳ <i>Chek tahlil qilinmoqda, iltimos kuting...</i>", parse_mode="HTML")
    file = await message.bot.get_file(photo_id)
    photo_bytes = await message.bot.download_file(file.file_path)
    detected_amount = await extract_receipt_amount(photo_bytes.read()) or 0
    
    # 1. Save to DB
    deposit_id = await add_deposit(user_id, detected_amount, photo_id)
    
    # 2. Notify Admin
    amount_text = f"💰 Aniqlangan summa: <b>{detected_amount:,} so'm</b>" if detected_amount else "⚠️ Summani aniqlab bo'lmadi."
    import html
    safe_name = html.escape(message.from_user.full_name)
    
    text = (
        "<b>💳 YANGI TO'LOV CHEKI (DEPOZIT)</b>\n━━━━━━━━━━━━━━\n\n"
        f"👤 Foydalanuvchi: {safe_name}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"{amount_text}\n"
        f"🔢 So'rov ID: <code>{deposit_id}</code>\n\n"
        "Buni admin panel > To'lovlar bo'limidan tasdiqlashingiz mumkin."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👁 Ko'rish", callback_data=f"dview_{deposit_id}")],
        [InlineKeyboardButton(text="💰 Tezkor tasdiqlash", callback_data=f"pay_app_{user_id}_{detected_amount}")]
    ])
    
    try:
        await message.bot.send_message(ADMIN_ID, text, reply_markup=kb, parse_mode="HTML")
        await message.answer(
            get_trans(lang, 'deposit_sent'),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_wallet")]])
        )
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")
        
    await state.clear()
    
@router.callback_query(F.data == "withdraw_request")
async def withdraw_request_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user = await get_user(callback.from_user.id)
    balance = user[6]
    if balance < 50000:
        return await callback.answer("❌ Minimal yechib olish miqdori 50,000 so'm.", show_alert=True)
    
    await state.set_state(PaymentStates.waiting_for_withdraw_amount)
    await callback.message.answer(
        "💸 <b>PUL YECHIB OLISH</b>\n━━━━━━━━━━━━━━\n\n"
        f"Mavjud balans: <b>{format_currency(balance)}</b>\n\n"
        "Qancha miqdorda pul yechmoqchisiz?\n"
        "(Faqat raqam kiriting, m-n: 50000)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏎ Orqaga", callback_data="close_wallet")]]),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(PaymentStates.waiting_for_withdraw_amount, F.text)
async def process_withdraw_amount(message: types.Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    balance = user[6]
    try:
        amount = float(message.text.replace(" ", ""))
        if amount < 50000:
            return await message.answer("❌ Minimal yechib olish miqdori 50,000 so'm.")
        if amount > balance:
            return await message.answer(f"❌ Balansingizda yetarli mablag' yo'q.\nMavjud: {format_currency(balance)}")
            
        await state.update_data(withdraw_amount=amount)
        await state.set_state(PaymentStates.waiting_for_withdraw_card)
        await message.answer("💳 <b>Karta raqamingizni va ism-sharifingizni kiriting:</b>\n\nMasalan: <code>8600123456789012 Aliyev Ali</code>", parse_mode="HTML")
    except:
        await message.answer("❌ Iltimos, faqat raqam kiriting!")

@router.message(PaymentStates.waiting_for_withdraw_card, F.text)
async def process_withdraw_card(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = int(data['withdraw_amount'])
    user_id = message.from_user.id
    details = message.text
    
    # Generate unique request ID
    request_id = uuid.uuid4().hex[:8]
    
    # 1. Save to DB
    await add_withdrawal_request(request_id, user_id, amount, details)
    
    # 2. Lock funds (deduct now, refund if rejected)
    await update_user_balance(user_id, -amount, f"Yechib olish so'rovi (ID: {request_id})", 'out')
    
    # 3. Send to admin
    import html
    safe_name = html.escape(message.from_user.full_name)
    safe_details = html.escape(details)
    
    text = (
        "<b>💸 YANGI YECHIB OLISH SO'ROVI</b>\n━━━━━━━━━━━━━━\n\n"
        f"👤 User: {safe_name}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💰 Miqdor: <b>{format_currency(int(amount))}</b>\n"
        f"💳 Rekvizitlar: <code>{safe_details}</code>\n"
        f"🔢 So'rov ID: <code>{request_id}</code>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"wth_done_{request_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"wth_rej_{request_id}")]
    ])
    
    user = await get_user(user_id)
    lang = user[8] if user else 'uz'
    
    try:
        await message.bot.send_message(ADMIN_ID, text, reply_markup=kb, parse_mode="HTML")
        await message.answer(get_trans(lang, 'withdraw_pending'), parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")
    
    await state.clear()

@router.message(F.text.in_({"👥 Do'stlarni taklif qilish", "👥 Пригласить друзей", "👥 Invite Friends"}))
async def show_referral_panel(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    if not user: return
    
    lang = user[8]
    ref_count = await get_referral_stats(user_id)
    ref_bonus_amount = int(await get_setting('ref_bonus', '500'))
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    
    text = (
        f"<b>👥 DO'STLARNI TAKLIF QILISH</b>\n\n"
        f"Botimizni do'stlaringizga tavsiya qiling va har bir ro'yxatdan o'tgan do'stingiz uchun "
        f"<b>{ref_bonus_amount:,} so'm</b> bonusga ega bo'ling!\n\n"
        f"📊 <b>Sizning statistikangiz:</b>\n"
        f"• Taklif qilinganlar: {ref_count} ta\n"
        f"• Jami ishlangan: {ref_count * ref_bonus_amount:,} so'm\n\n"
        f"🔗 <b>Tavsiya havola:</b>\n<code>{ref_link}</code>"
    )
    
    invite_text = get_trans(lang, 'invite_msg_text').format(ref_link=ref_link)
    # Removing 'url' param to avoid duplication at the beginning of the message
    share_url = f"https://t.me/share/url?text={urllib.parse.quote(invite_text, safe='')}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Do'stlarga ulashish", url=share_url)],
        [InlineKeyboardButton(text="🔗 Havolani nusxalash", callback_data=f"copy_ref_{user_id}")],
        [InlineKeyboardButton(text="👥 Do'stlar ro'yxati", callback_data="ref_list")],
        [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_wallet")]
    ])
    
    # Try to send with banner, fallback to text
    banner_path = os.path.join("assets", "banner.png")
    
    try:
        if os.path.exists(banner_path):
            photo = FSInputFile(banner_path)
            await message.answer_photo(photo, caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("copy_ref_"))
async def copy_ref_link(callback: types.CallbackQuery):
    user_id = int(callback.data.replace("copy_ref_", ""))
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    await callback.answer(f"✅ Havola: {ref_link}", show_alert=True)


@router.callback_query(F.data == "close_wallet")
async def close_wallet(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass
    await callback.answer()



# ==============================
# === DRIVER TARIFF PURCHASE ===
# ==============================

@router.callback_query(F.data == "driver_tariffs")
async def show_driver_tariffs(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    if not user or user[4] != 'driver':
        return await callback.answer("Bu bo'lim faqat haydovchilar uchun.", show_alert=True)

    balance = user[6]
    sub = await get_driver_sub_status(user_id)

    # Build subscription status text
    expiry_text = "❌ Muddatli tarif yo'q"
    if sub["expiry"]:
        try:
            exp = datetime.fromisoformat(str(sub["expiry"]))
            if exp > datetime.now():
                expiry_text = f"✅ Amal qiladi: <b>{exp.strftime('%d.%m.%Y %H:%M')}</b> gacha"
            else:
                expiry_text = "⏰ Muddatli tarif tugagan"
        except:
            pass

    pax_text = f"👤 Yo'lovchi kvotasi: <b>{sub['pax_quota']}</b> ta"
    parcel_text = f"📦 Pochta kvotasi: <b>{sub['parcel_quota']}</b> ta"

    # Get prices
    p_daily = int(await get_setting('tariff_daily_price', '10000'))
    p_monthly = int(await get_setting('tariff_monthly_price', '200000'))
    p_pax = int(await get_setting('tariff_pax_unit_price', '5000'))
    p_parcel = int(await get_setting('tariff_parcel_unit_price', '3000'))
    units_pax = int(await get_setting('tariff_pax_units', '10'))
    units_parcel = int(await get_setting('tariff_parcel_units', '10'))

    text = (
        f"<b>📋 HAYDOVCHI TARIFLARI</b>\n\n"
        f"💰 Hisobingiz: <b>{balance:,} so'm</b>\n\n"
        f"<b>📊 Joriy holat:</b>\n"
        f"{expiry_text}\n"
        f"{pax_text}\n"
        f"{parcel_text}\n\n"
        f"<b>🛒 Tariflarni sotib olish:</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🌅 Kunlik (1 kun) — {p_daily:,} so'm",
            callback_data="buy_tariff_daily"
        )],
        [InlineKeyboardButton(
            text=f"🗓 Oylik (30 kun) — {p_monthly:,} so'm",
            callback_data="buy_tariff_monthly"
        )],
        [InlineKeyboardButton(
            text=f"👤 Yo'lovchi kvotasi ({units_pax} ta) — {p_pax:,} so'm",
            callback_data="buy_tariff_pax"
        )],
        [InlineKeyboardButton(
            text=f"📦 Pochta kvotasi ({units_parcel} ta) — {p_parcel:,} so'm",
            callback_data="buy_tariff_parcel"
        )],
    ])
    
    # Priority switch check
    if await get_setting('btn_priority', '1') == '1':
        kb.inline_keyboard.insert(-1, [InlineKeyboardButton(text=get_trans(user[8], 'priority_buy'), callback_data="buy_priority_menu")])
    
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="close_wallet")])

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer()

async def _purchase_tariff(callback: types.CallbackQuery, plan_type: str):
    """Shared purchase logic for all plan types."""
    user_id = callback.from_user.id
    user = await get_user(user_id)
    if not user or user[4] != 'driver':
        return await callback.answer("Bu bo'lim faqat haydovchilar uchun.", show_alert=True)

    lang = user[8] if user else 'uz'
    balance = user[6]
    key_map = {
        'daily':   ('tariff_daily_price', '10000', 1, 'daily'),
        'monthly': ('tariff_monthly_price', '200000', 30, 'monthly'),
        'pax':     ('tariff_pax_unit_price', '5000', 0, 'pax'),
        'parcel':  ('tariff_parcel_unit_price', '3000', 0, 'parcel'),
    }
    setting_key, default, days, kind = key_map[plan_type]
    price = int(await get_setting(setting_key, default))

    if balance < price:
        return await callback.answer(
            f"❌ Balans yetarli emas!\nKerak: {price:,} so'm | Mavjud: {balance:,} so'm",
            show_alert=True
        )

    # Deduct balance
    async with db_session() as db:
        await update_user_balance_conn(db, user_id, -price, f"Tarif sotib olindi: {plan_type}", 'out')
        await db.commit()

    # Apply plan
    if kind in ('daily', 'monthly'):
        expiry = await extend_driver_subscription(user_id, days)
        exp_str = datetime.fromisoformat(expiry).strftime('%d.%m.%Y %H:%M')
        msg = f"✅ <b>Tarif faollashtirildi!</b>\nMuddati: <b>{exp_str}</b> gacha."
    else:
        units_key = 'tariff_pax_units' if kind == 'pax' else 'tariff_parcel_units'
        units = int(await get_setting(units_key, '10'))
        if kind == 'pax':
            await add_driver_quota(user_id, pax=units)
            msg = f"✅ <b>Kvota qo'shildi!</b>\n👤 Yo'lovchi: +<b>{units}</b> ta"
        else:
            await add_driver_quota(user_id, pc=units)
            msg = f"✅ <b>Kvota qo'shildi!</b>\n📦 Pochta: +<b>{units}</b> ta"

    await callback.answer("✅ Muvaffaqiyatli!")
    await callback.message.answer(
        msg, 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_wallet")]]),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "buy_tariff_daily")
async def buy_daily(callback: types.CallbackQuery):
    await _purchase_tariff(callback, 'daily')

@router.callback_query(F.data == "buy_tariff_monthly")
async def buy_monthly(callback: types.CallbackQuery):
    await _purchase_tariff(callback, 'monthly')

@router.callback_query(F.data == "buy_tariff_pax")
async def buy_pax(callback: types.CallbackQuery):
    await _purchase_tariff(callback, 'pax')

@router.callback_query(F.data == "buy_tariff_parcel")
async def buy_parcel(callback: types.CallbackQuery):
    await _purchase_tariff(callback, 'parcel')

@router.callback_query(F.data == "buy_priority_menu")
async def show_priority_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    lang = user[8] if user else 'uz'
    
    price = int(await get_setting('priority_price_daily', '5000'))
    delay = int(await get_setting('priority_delay', '10'))
    
    # Check current status
    async with db_session() as db:
        async with db.execute("SELECT priority_expiry FROM drivers WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            expiry = row[0] if row else None
            
    status_text = get_trans(lang, 'priority_none')
    if expiry:
        try:
            exp_dt = datetime.fromisoformat(str(expiry))
            if exp_dt > datetime.now():
                status_text = get_trans(lang, 'priority_active').format(date=exp_dt.strftime('%d.%m.%Y %H:%M'))
        except: pass
        
    text = get_trans(lang, 'priority_info').format(delay=delay, price=price)
    text = f"<b>{status_text}</b>\n\n{text}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🌅 1 kun — {price:,} so'm", callback_data=f"buy_prio_1")],
        [InlineKeyboardButton(text=f"🗓 7 kun — {price*7*0.9:,} so'm (10% skitka)", callback_data=f"buy_prio_7")],
        [InlineKeyboardButton(text=f"🚀 30 kun — {price*30*0.8:,} so'm (20% skitka)", callback_data=f"buy_prio_30")],
        [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="driver_tariffs")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("buy_prio_"))
async def process_buy_priority(callback: types.CallbackQuery):
    days = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    user = await get_user(user_id)
    lang = user[8] if user else 'uz'
    
    daily_price = int(await get_setting('priority_price_daily', '5000'))
    
    # Apply discounts
    total_price = daily_price * days
    if days == 7: total_price = int(total_price * 0.9)
    if days == 30: total_price = int(total_price * 0.8)
    
    if user[6] < total_price:
        return await callback.answer(f"❌ Balans yetarli emas! Kerak: {total_price:,} so'm", show_alert=True)
        
    new_expiry = await purchase_priority(user_id, days, total_price)
    exp_str = datetime.fromisoformat(new_expiry).strftime('%d.%m.%Y %H:%M')
    
    await callback.answer("✅ Muvaffaqiyatli!")
    await callback.message.answer(f"🚀 <b>Ustuvorlik faollashtirildi!</b>\nMuddati: <b>{exp_str}</b> gacha.", parse_mode="HTML")
    await show_priority_menu(callback)

# --- 💸 WITHDRAW CALLBACKS ---

@router.callback_query(F.data.startswith("wth_done_"))
async def withdraw_done(callback: types.CallbackQuery):
    # wth_done_{request_id}
    request_id = callback.data.split("_")[2]
    
    req = await get_withdrawal_request(request_id)
    if not req: return await callback.answer("So'rov topilmadi.")
    if req[4] != 'pending': return await callback.answer(f"Bu so'rov allaqachon {req[4]}.")
    
    user_id = req[1]
    amount = int(req[2])
    
    # Mark as approved in DB
    await update_withdrawal_status(request_id, 'approved')
    
    # Notify user
    lang = await get_user_language(user_id)
    msg = get_trans(lang, 'withdraw_approved').format(amount=format_currency(amount))
    try:
        await callback.message.bot.send_message(user_id, msg, parse_mode="HTML")
    except:
        pass
    
    await callback.message.edit_text(callback.message.text + "\n\n✅ <b>TASDIQLANDI (Muvaffaqiyatli to'landi)</b>", parse_mode="HTML")
    await callback.answer("Tasdiqlandi")

@router.callback_query(F.data.startswith("wth_rej_"))
async def withdraw_rejected_callback(callback: types.CallbackQuery):
    # wth_rej_{request_id}
    request_id = callback.data.split("_")[2]
    
    req = await get_withdrawal_request(request_id)
    if not req: return await callback.answer("So'rov topilmadi.")
    if req[4] != 'pending': return await callback.answer(f"Bu so'rov allaqachon {req[4]}.")
    
    user_id = req[1]
    amount = int(req[2])
    
    # Refund locked funds
    await update_user_balance(user_id, amount, f"Yechib olish rad etildi (ID: {request_id}) - Qaytarildi", 'in')
    
    # Mark as rejected in DB
    await update_withdrawal_status(request_id, 'rejected')
    
    # Notify user
    lang = await get_user_language(user_id)
    msg = get_trans(lang, 'withdraw_rejected')
    try:
        await callback.message.bot.send_message(user_id, msg, parse_mode="HTML")
    except:
        pass
    
    await callback.message.edit_text(callback.message.text + "\n\n❌ <b>RAD ETILDI (Pul qaytarildi)</b>", parse_mode="HTML")
    await callback.answer("Rad etildi")
