from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from utils.states import AdminStates
from database.db import get_all_promocodes, add_promocode, delete_promocode, log_action
from utils.formatters import format_currency
from .base import admin_filter

router = Router()

@router.callback_query(F.data == "adm_promo", admin_filter)
async def adm_promo_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    
    promos = await get_all_promocodes()
    
    text = "<b>🎫 PROMOKODLAR BOSHQARUVI</b>\n━━━━━━━━━━━━━━\n\n"
    
    kb = []
    if promos:
        for p in promos:
            # p: 0=code, 1=amount, 2=usage_limit, 3=used_count, 4=expiry
            status = "⏳" if p[4] else "♾"
            text += f"🎫 <b>{p[0]}</b> {status}\n💰 Miqdor: {format_currency(int(p[1]))}\n📊 Ishlatildi: {p[3]}/{p[2]}\n\n"
            kb.append([
                InlineKeyboardButton(text=f"🗑 O'chirish: {p[0]}", callback_data=f"del_promo_{p[0]}")
            ])
    else:
        text += "<i>Hozircha promokodlar yo'q.</i>\n\n"
        
    kb.append([InlineKeyboardButton(text="➕ Yangi promokod yaratish", callback_data="add_promo")])
    kb.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data.startswith("del_promo_"), admin_filter)
async def del_promo_handler(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.replace("del_promo_", "")
    await delete_promocode(code)
    await log_action(callback.from_user.id, "delete_promo", f"Code: {code}")
    await callback.answer(f"✅ {code} o'chirildi", show_alert=True)
    await adm_promo_menu(callback, state)

@router.callback_query(F.data == "add_promo", admin_filter)
async def add_promo_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.adding_promo_code)
    await callback.message.edit_text("<b>🎫 YANGI PROMOKOD</b>\n━━━━━━━━━━━━━━\nPromokod so'zini kiriting (masalan: <b>NAVROZ</b>):",
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_promo")]]),
                                    parse_mode="HTML")

@router.message(AdminStates.adding_promo_code, F.text, admin_filter)
async def process_promo_code(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    if len(code) < 3 or len(code) > 20:
        return await message.answer("❌ Promokod uzunligi 3 dan 20 harfgacha bo'lishi kerak. Qaytadan kiriting:")
    
    await state.update_data(promo_code=code)
    await state.set_state(AdminStates.adding_promo_amount)
    await message.answer(f"🎫 Kod: <b>{code}</b>\n\n💰 Endi beriladigan summani kiriting (masalan: 10000):", parse_mode="HTML")

@router.message(AdminStates.adding_promo_amount, F.text, admin_filter)
async def process_promo_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Faqat raqam kiriting:")
    
    amount = int(message.text)
    if amount < 1000:
        return await message.answer("❌ Minimal qiymat 1,000 so'm. Qaytadan kiriting:")
        
    await state.update_data(promo_amount=amount)
    await state.set_state(AdminStates.adding_promo_limit)
    await message.answer(f"💰 Summa: <b>{format_currency(amount)}</b>\n\n👥 Necha marta foydalanish mumkin? Limitni kiriting (masalan: 100):", parse_mode="HTML")

@router.message(AdminStates.adding_promo_limit, F.text, admin_filter)
async def process_promo_limit(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Faqat raqam kiriting:")
        
    limit = int(message.text)
    data = await state.get_data()
    code = data['promo_code']
    amount = data['promo_amount']
    
    success = await add_promocode(code, amount, limit)
    
    if success:
        await log_action(message.from_user.id, "add_promo", f"Code: {code}, Amt: {amount}, Limit: {limit}")
        await message.answer(f"✅ <b>Promokod muvaffaqiyatli yaratildi!</b>\n━━━━━━━━━━━━━━\n🎫 Kod: <code>{code}</code>\n💰 Summa: {format_currency(amount)}\n👥 Limit: {limit} marta", parse_mode="HTML")
    else:
        await message.answer("❌ Xatolik yuz berdi. Bunday kod mavjud bo'lishi mumkin.")
        
    await state.clear()
    
    # Back to menu logic using a dummy callback
    from aiogram.types import CallbackQuery
    # Since we can't easily mock CallbackQuery, just send the main menu
    from .base import get_admin_main_kb
    from database.db import get_admin
    adm = await get_admin(message.from_user.id)
    perms = adm[2] if adm else 'all'
    await message.answer("<b>💎 PREMIUM ADMIN PANEL</b>\n━━━━━━━━━━━━━━\nBo'limni tanlang:", reply_markup=get_admin_main_kb(message.from_user.id, perms), parse_mode="HTML")
