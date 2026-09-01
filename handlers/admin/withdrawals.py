from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import (
    get_pending_withdrawals, get_withdrawal_request, update_withdrawal_status, 
    update_user_balance, get_user_language, get_pending_deposits, get_deposit,
    update_deposit_status, get_user
)
from .base import admin_filter
from utils.formatters import format_currency
from utils.locales import get_trans

router = Router()

@router.callback_query(F.data.in_({"adm_finance", "adm_withdrawals"}), admin_filter)
async def payments_main_menu(callback: types.CallbackQuery):
    await callback.answer()
    
    pending_w = await get_pending_withdrawals()
    pending_d = await get_pending_deposits()
    
    text = (
        "💳 <b>MOLIYA VA TO'LOVLAR MARKAZI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📥 Kutilayotgan tushumlar (Cheklar): <b>{len(pending_d)} ta</b>\n"
        f"📤 Kutilayotgan chiqimlar (Yechish): <b>{len(pending_w)} ta</b>\n\n"
        "Boshqarish uchun bo'limni tanlang:"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"📥 Tushumlar ({len(pending_d)})", callback_data="adm_list_deposits"),
            InlineKeyboardButton(text=f"📤 Chiqimlar ({len(pending_w)})", callback_data="adm_list_withdrawals")
        ],
        [InlineKeyboardButton(text="🎫 Promokodlar boshqaruvi", callback_data="adm_promo")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm_list_withdrawals", admin_filter)
async def list_pending_withdrawals(callback: types.CallbackQuery):
    await callback.answer()
    records = await get_pending_withdrawals()
    if not records:
        return await callback.answer("Hozircha chiqim so'rovlari yo'q.", show_alert=True)
        
    text = "<b>📤 KUTILAYOTGAN PULLARNI YECHISH</b>\n\n"
    import html
    kb = []
    for w in records[:15]:
        safe_name = html.escape(w[6])
        text += f"👤 {safe_name} | 💰 {int(w[2]):,} so'm\n"
        kb.append([InlineKeyboardButton(text=f"✅ {w[6]} - {int(w[2]):,} so'm", callback_data=f"wview_{w[0]}")])
    
    kb.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_withdrawals")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data == "adm_list_deposits", admin_filter)
async def list_pending_deposits(callback: types.CallbackQuery):
    await callback.answer()
    records = await get_pending_deposits()
    if not records:
        return await callback.answer("Hozircha tushum so'rovlari (cheklar) yo'q.", show_alert=True)
        
    text = "<b>📥 KUTILAYOTGAN TO'LOV CHEKLARI</b>\n\n"
    import html
    kb = []
    for d in records[:15]:
        safe_name = html.escape(d[5])
        text += f"👤 {safe_name} | 💰 {int(d[2]):,} so'm\n"
        kb.append([InlineKeyboardButton(text=f"👁 {d[5]} - {int(d[2]):,} so'm", callback_data=f"dview_{d[0]}")])
    
    kb.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_withdrawals")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data.startswith("dview_"), admin_filter)
async def view_deposit_detail(callback: types.CallbackQuery):
    await callback.answer()
    dep_id = int(callback.data.split("_")[1])
    dep = await get_deposit(dep_id)
    if not dep: return await callback.answer("Topilmadi.")
    
    user = await get_user(dep[1])
    
    import html
    safe_name = html.escape(user[1])
    
    text = (
        f"<b>📥 TO'LOV CHEKI</b>\n━━━━━━━━━━━━━━\n\n"
        f"👤 Foydalanuvchi: {safe_name}\n"
        f"🆔 User ID: <code>{user[0]}</code>\n"
        f"💰 Aniqlangan summa: <b>{format_currency(int(dep[2]))}</b>\n"
        f"📅 Sana: {dep[5]}\n\n"
        "Hisobni to'ldirish uchun summani tasdiqlang yoki rad eting:"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay_app_{user[0]}_{int(dep[2])}_{dep_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay_rej_{user[0]}_{dep_id}")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_list_deposits")]
    ])
    
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.bot.send_photo(callback.from_user.id, dep[3], caption=text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("pay_app_"), admin_filter)
async def approve_deposit(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    u_id = int(parts[2])
    amount = float(parts[3])
    dep_id = int(parts[4]) if len(parts) > 4 else None
    
    # 1. Update balance
    await update_user_balance(u_id, amount, "Hisob to'ldirildi (Chek orqali)", 'in')
    
    # 2. Update status in DB
    if dep_id:
        await update_deposit_status(dep_id, 'approved')
        
    # 3. Notify user
    lang = await get_user_language(u_id)
    msg = get_trans(lang, 'deposit_approved').format(amount=format_currency(int(amount)))
    try: await callback.bot.send_message(u_id, msg, parse_mode="HTML")
    except: pass
    
    await callback.answer("✅ To'lov tasdiqlandi va balansga qo'shildi!", show_alert=True)
    if dep_id:
        try:
            await callback.message.delete()
        except:
            pass
        await payments_main_menu(callback)
    else:
        await callback.message.edit_reply_markup(reply_markup=None)

@router.callback_query(F.data.startswith("pay_rej_"), admin_filter)
async def reject_deposit(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    u_id = int(parts[2])
    dep_id = int(parts[3]) if len(parts) > 3 else None
    
    if dep_id:
        await update_deposit_status(dep_id, 'rejected')
        
    lang = await get_user_language(u_id)
    msg = get_trans(lang, 'deposit_rejected')
    try: await callback.bot.send_message(u_id, msg, parse_mode="HTML")
    except: pass
    
    await callback.answer("❌ Rad etildi.", show_alert=True)
    if dep_id:
        try:
            await callback.message.delete()
        except:
            pass
        await payments_main_menu(callback)
    else:
        await callback.message.edit_reply_markup(reply_markup=None)

@router.callback_query(F.data.startswith("wview_"), admin_filter)
async def view_withdrawal_detail(callback: types.CallbackQuery):
    await callback.answer()
    req_id = callback.data.split("_")[1]
    req = await get_withdrawal_request(req_id)
    if not req: return await callback.answer("Topilmadi.")
    
    user = await get_user(req[1])
    
    text = (
        f"<b>📤 PUL YECHIB OLISH SO'ROVI</b>\n━━━━━━━━━━━━━━\n\n"
        f"👤 Foydalanuvchi: {user[1]}\n"
        f"🆔 User ID: <code>{user[0]}</code>\n"
        f"💰 Miqdor: <b>{format_currency(int(req[2]))}</b>\n"
        f"💳 Rekvizitlar: <code>{req[3]}</code>\n"
        f"📅 Sana: {req[5]}\n"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ To'landi", callback_data=f"wth_done_{req_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"wth_rej_{req_id}")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_list_withdrawals")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


