from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import (
    get_orders_by_status, get_order, get_user, update_order_status,
    get_orders_deep_analysis, reset_all_orders
)
from utils.states import AdminStates
from .base import admin_filter
from datetime import datetime

router = Router()

@router.callback_query(F.data == "adm_orders", admin_filter)
async def adm_orders_menu(callback: types.CallbackQuery):
    await callback.answer()
    d = await get_orders_deep_analysis()
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    total_closed = (d['finished_count'] or 0) + (d['cancelled_count'] or 0)
    finish_rate = round((d['finished_count'] / total_closed) * 100, 1) if total_closed > 0 else 0
    cancel_rate = round((d['cancelled_count'] / total_closed) * 100, 1) if total_closed > 0 else 0

    # Top routes text
    routes_text = ""
    for r in d['top_routes'][:3]:
        routes_text += f"  • {r[0]} ➔ {r[1]}: <b>{r[2]} ta</b> (~{int(r[3] or 0):,} s)\n"
    if not routes_text:
        routes_text = "  • Hozircha buyurtmalar yo'q\n"

    text = (
        f"📦 <b>BUYURTMALAR — 100% TO'LIQ TAHLILI</b>\n"
        f"🕐 <i>{now}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>BUYURTMALAR SONI:</b>\n"
        f"  📦 Jami buyurtmalar:   <b>{d['total_orders']:,}</b> ta\n"
        f"  📅 Bugungi yangi:      <b>{d['today_orders']:,}</b> ta\n"
        f"  🚕 Taksi buyurtmalari: <b>{d['taxi_count']:,}</b> ta\n"
        f"  📫 Pochta / Yuk:       <b>{d['parcel_count']:,}</b> ta\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡️ <b>HOLATLAR BO'YICHA:</b>\n"
        f"  ⏳ Kutilayotgan:       <b>{d['pending_count']:,}</b> ta\n"
        f"  ⚡️ Jarayonda (Aktiv):  <b>{d['active_count']:,}</b> ta\n"
        f"  ✅ Yakunlangan:        <b>{d['finished_count']:,}</b> ta ({finish_rate}%)\n"
        f"  ❌ Bekor qilingan:     <b>{d['cancelled_count']:,}</b> ta ({cancel_rate}%)\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>MOLIYA VA AYLANMA:</b>\n"
        f"  💵 Jami aylanma:       <b>{int(d['total_revenue']):,}</b> so'm\n"
        f"  📈 Bugungi tushum:     <b>{int(d['today_revenue']):,}</b> so'm\n"
        f"  📊 O'rtacha narx:      <b>{int(d['avg_price']):,}</b> so'm\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 <b>ENG FAOL YO'NALISHLAR (TOP 3):</b>\n"
        f"{routes_text}"
        f"━━━━━━━━━━━━━━━━━━━━━━━"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Buyurtma qidirish (ID)", callback_data="adm_search_order")],
        [
            InlineKeyboardButton(text=f"⏳ Kutilmoqda ({d['pending_count']})", callback_data="adm_ord_list_pending"),
            InlineKeyboardButton(text=f"⚡️ Jarayonda ({d['active_count']})", callback_data="adm_ord_list_active")
        ],
        [
            InlineKeyboardButton(text=f"✅ Yakunlangan ({d['finished_count']})", callback_data="adm_ord_list_finished"),
            InlineKeyboardButton(text=f"❌ Bekor qilingan ({d['cancelled_count']})", callback_data="adm_ord_list_cancelled")
        ],
        [InlineKeyboardButton(text="📥 To'liq Excel hisobot yuklash", callback_data="export_excel")],
        [InlineKeyboardButton(text="🗑 Barcha buyurtmalarni o'chirish", callback_data="adm_ord_reset_confirm")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")]
    ])

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm_search_order", admin_filter)
async def adm_search_order_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.searching_order)
    await callback.answer()
    try:
        await callback.message.edit_text(
            "🔍 <b>Buyurtma ID raqamini kiriting:</b>\n\nMasalan: <code>45</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_orders")]]),
            parse_mode="HTML"
        )
    except:
        pass


@router.message(AdminStates.searching_order, F.text, admin_filter)
async def process_search_order(message: types.Message, state: FSMContext):
    await state.clear()
    txt = message.text.strip().replace("#", "")
    if not txt.isdigit():
        return await message.answer("❌ Iltimos, faqat raqamdan iborat buyurtma ID kiriting!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_orders")]]))
        
    o_id = int(txt)
    order = await get_order(o_id)
    if not order:
        return await message.answer(f"❌ <b>#{o_id} raqamli buyurtma topilmadi!</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_orders")]], parse_mode="HTML"))
        
    p = await get_user(order[1])
    d = await get_user(order[2]) if order[2] else None
    status = order[11]
    import html
    p_name = html.escape(p[1]) if p else "Mijoz"
    p_phone = p[2] if p else "-"
    d_name = html.escape(d[1]) if d else "Topilmadi"
    d_phone = d[2] if d else "-"

    text = (
        f"📦 <b>BUYURTMA TAFSILOTLARI #{o_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 <b>Qayerdan:</b> {order[3]}\n"
        f"🏁 <b>Qayerga:</b> {order[4]}\n"
        f"💰 <b>Narxi:</b> <b>{int(order[5]):,} so'm</b>\n"
        f"👥 <b>Yo'lovchilar:</b> {order[6]} ta\n"
        f"🚗 <b>Tarif:</b> {order[13] if len(order)>13 and order[13] else 'Standard'}\n"
        f"📊 <b>Holati:</b> <code>{status.upper()}</code>\n"
        f"⏰ <b>Vaqt:</b> {order[7] or 'Hozir'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Yo'lovchi:</b> {p_name} (📞 {p_phone})\n"
        f"🚗 <b>Haydovchi:</b> {d_name} (📞 {d_phone})\n"
    )
    rows = []
    if status in ['pending', 'active', 'accepted', 'arrived']:
        rows.append([InlineKeyboardButton(text="❌ Bekor qilish (Admin)", callback_data=f"adm_ocan_{o_id}")])
    rows.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_orders")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")



@router.callback_query(F.data.startswith("adm_ord_list_"), admin_filter)
async def adm_orders_list(callback: types.CallbackQuery):
    await callback.answer()
    status = callback.data.replace("adm_ord_list_", "")
    orders = await get_orders_by_status(status)
    if not orders: return await callback.answer(f"{status} holatidagi buyurtmalar yo'q.", show_alert=True)
    
    text = f"📋 <b>{status.upper()} BUYURTMALAR (Oxirgi 20 ta):</b>\n━━━━━━━━━━━━━━\n\n"
    kb = []
    for o in orders[:20]:
        o_id, p_id, d_id, f_loc, t_loc, price, p_count = o[0], o[1], o[2], o[3], o[4], o[5], o[6]
        text += f"• #{o_id} | {f_loc} ➔ {t_loc} | {int(price):,} so'm\n"
        kb.append([InlineKeyboardButton(text=f"👁 #{o_id} — {f_loc} ➔ {t_loc}", callback_data=f"adm_oview_{o_id}")])
        
    kb.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_orders")])
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    except:
        pass


@router.callback_query(F.data.startswith("adm_oview_"), admin_filter)
async def adm_order_view(callback: types.CallbackQuery):
    await callback.answer()
    o_id = int(callback.data.replace("adm_oview_", ""))
    order = await get_order(o_id)
    if not order: return await callback.answer("Buyurtma topilmadi.")
    
    p = await get_user(order[1])
    d = await get_user(order[2]) if order[2] else None
    status = order[11]
    import html
    p_name = html.escape(p[1]) if p else "Mijoz"
    p_phone = p[2] if p else "-"
    d_name = html.escape(d[1]) if d else "Topilmadi"
    d_phone = d[2] if d else "-"

    text = (
        f"📦 <b>BUYURTMA TAFSILOTLARI #{o_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 <b>Qayerdan:</b> {order[3]}\n"
        f"🏁 <b>Qayerga:</b> {order[4]}\n"
        f"💰 <b>Narxi:</b> <b>{int(order[5]):,} so'm</b>\n"
        f"👥 <b>Yo'lovchilar:</b> {order[6]} ta\n"
        f"🚗 <b>Tarif:</b> {order[13] if len(order)>13 and order[13] else 'Standard'}\n"
        f"📊 <b>Holati:</b> <code>{status.upper()}</code>\n"
        f"⏰ <b>Vaqt:</b> {order[7] or 'Hozir'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Yo'lovchi:</b> {p_name} (📞 {p_phone})\n"
        f"🚗 <b>Haydovchi:</b> {d_name} (📞 {d_phone})\n"
    )
    rows = []
    if status in ['pending', 'active', 'accepted', 'arrived']:
        rows.append([InlineKeyboardButton(text="❌ Bekor qilish (Admin)", callback_data=f"adm_ocan_{o_id}")])
    rows.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_orders")])
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    except:
        pass


@router.callback_query(F.data.startswith("adm_ocan_"), admin_filter)
async def adm_order_cancel(callback: types.CallbackQuery):
    o_id = int(callback.data.replace("adm_ocan_", ""))
    await update_order_status(o_id, 'cancelled')
    await callback.answer(f"#{o_id} bekor qilindi.")
    await adm_orders_menu(callback)


# ─── BARCHA BUYURTMALARNI O'CHIRISH (2-bosqichli tasdiqlash) ───────────────

@router.callback_query(F.data == "adm_ord_reset_confirm", admin_filter)
async def adm_orders_reset_confirm(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ HA, HAMMASINI O'CHIR!", callback_data="adm_ord_reset_final")],
        [InlineKeyboardButton(text="❌ YO'Q, BEKOR", callback_data="adm_orders")]
    ])
    try:
        await callback.message.edit_text(
            "🗑 <b>BARCHA BUYURTMALARNI O'CHIRISH</b>\n"
            "━━━━━━━━━━━━━━\n\n"
            "⚠️ <b>DIQQAT!</b> Bu amal <b>qaytarib bo'lmaydi!</b>\n\n"
            "Barcha buyurtmalar (pending, active, finished, cancelled) "
            "bazadan butunlay o'chirib tashlanadi.\n\n"
            "<i>Davom etishni xohlaysizmi?</i>",
            reply_markup=kb,
            parse_mode="HTML"
        )
    except:
        pass
    await callback.answer()


@router.callback_query(F.data == "adm_ord_reset_final", admin_filter)
async def adm_orders_reset_final(callback: types.CallbackQuery):
    deleted_count = await reset_all_orders()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_orders")]
    ])
    try:
        await callback.message.edit_text(
            f"✅ <b>MUVAFFAQIYATLI O'CHIRILDI!</b>\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"🗑 Jami <b>{deleted_count:,} ta</b> buyurtma bazadan o'chirildi.\n"
            f"📊 Buyurtmalar hisobi noldan boshlandi.",
            reply_markup=kb,
            parse_mode="HTML"
        )
    except:
        pass
    await callback.answer(f"✅ {deleted_count} ta buyurtma o'chirildi!")
