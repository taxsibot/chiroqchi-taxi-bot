from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_all_auto_replies, add_auto_reply, delete_auto_reply, clear_all_auto_replies
from utils.states import AdminStates
from .base import admin_filter

router = Router()

@router.callback_query(F.data == "adm_autoreply", admin_filter)
async def adm_autoreply_menu(callback: types.CallbackQuery):
    await callback.answer()
    replies = await get_all_auto_replies()
    
    text = (
        "🤖 <b>AVTO-JAVOB (FAQ) BOSHQARUVI</b>\n━━━━━━━━━━━━━━\n\n"
        "Foydalanuvchi ma'lum bir so'zni yozganda bot avtomatik javob beradi.\n\n"
        "<b>Mavjud avto-javoblar:</b>\n"
    )
    
    kb_rows = []
    if not replies:
        text += "<i>Hozircha avto-javoblar yo'q.</i>"
    else:
        for rid, kw, rep in replies:
            text += f"🔹 <b>{kw}</b> — {rep[:30]}...\n"
            kb_rows.append([InlineKeyboardButton(text=f"🗑 {kw}", callback_data=f"del_ar_{rid}")])
            
    if replies:
        kb_rows.append([InlineKeyboardButton(text="🗑 Barchasini o'chirish", callback_data="clear_all_ar")])
        
    kb_rows.append([InlineKeyboardButton(text="➕ Yangi qo'shish", callback_data="add_ar")])
    kb_rows.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")

@router.callback_query(F.data == "add_ar", admin_filter)
async def add_ar_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_ar_keyword)
    await callback.answer()
    await callback.message.edit_text(
        "📝 <b>Yangi avto-javob qo'shish</b>\n\n"
        "Foydalanuvchi yuboradigan <b>Kalit so'zni</b> kiriting:\n"
        "(Masalan: <i>narxlar</i>)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_autoreply")]]),
        parse_mode="HTML"
    )

@router.message(AdminStates.waiting_for_ar_keyword, admin_filter)
async def process_ar_keyword(message: types.Message, state: FSMContext):
    await state.update_data(ar_kw=message.text.lower().strip())
    await state.set_state(AdminStates.waiting_for_ar_reply)
    await message.answer(
        f"✅ Kalit so'z: <b>{message.text}</b>\n\n"
        f"Endi ushbu so'zga beriladigan <b>Javob matnini</b> kiriting:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_autoreply")]]),
        parse_mode="HTML"
    )

@router.message(AdminStates.waiting_for_ar_reply, admin_filter)
async def process_ar_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    kw = data['ar_kw']
    reply = message.text
    
    await add_auto_reply(kw, reply)
    await state.clear()
    
    await message.answer(
        f"✅ <b>Muvaffaqiyatli saqlandi!</b>\n\n"
        f"🔑 Kalit: <code>{kw}</code>\n"
        f"💬 Javob: {reply}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Menyoga qaytish", callback_data="adm_autoreply")]]),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("del_ar_"), admin_filter)
async def del_ar_handler(callback: types.CallbackQuery):
    rid = int(callback.data.replace("del_ar_", ""))
    await delete_auto_reply(rid)
    await callback.answer("O'chirildi.")
    await adm_autoreply_menu(callback)
@router.callback_query(F.data == "clear_all_ar", admin_filter)
async def clear_all_ar_handler(callback: types.CallbackQuery):
    await clear_all_auto_replies()
    await callback.answer("✅ Barcha avto-javoblar o'chirildi.", show_alert=True)
    await adm_autoreply_menu(callback)
