from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from database.db import get_detailed_stats, get_user_full_report, get_system_deep_audit
from utils.states import AdminStates
from .base import admin_filter
import os
from datetime import datetime

router = Router()

@router.callback_query(F.data == "adm_stats", admin_filter)
async def stats_menu(callback: types.CallbackQuery):
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Bugun", callback_data="stats_today"),
         InlineKeyboardButton(text="🗓 Hafta", callback_data="stats_weekly"),
         InlineKeyboardButton(text="📊 Oy", callback_data="stats_monthly")],
        [InlineKeyboardButton(text="🔍 360° To'liq Tahlil", callback_data="stats_deep_audit")],
        [InlineKeyboardButton(text="📥 Baza (Excel)", callback_data="export_excel"),
         InlineKeyboardButton(text="📝 Hisobot (Word)", callback_data="export_word")],
        [InlineKeyboardButton(text="📅 Sana bo'yicha hisobot", callback_data="rp_date")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")]
    ])
    try:
        await callback.message.edit_text("📊 <b>STATISTIKA VA HISOBOTLAR MARKAZI:</b>\n\nDavrni tanlang yoki hisobot yuklab oling:", reply_markup=kb, parse_mode="HTML")
    except:
        pass



@router.callback_query(F.data == "stats_deep_audit", admin_filter)
async def show_deep_audit(callback: types.CallbackQuery):
    await callback.answer("⏳ Tahlil qilinmoqda...")
    
    try:
        msg = await callback.message.edit_text("🔄 <b>To'liq tahlil bajarilmoqda...</b>\n<i>Barcha ma'lumotlar yig'ilmoqda, bir oz kuting.</i>", parse_mode="HTML")
    except:
        msg = None

    d = await get_system_deep_audit()
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    # Language distribution
    lang_map = {'uz': '🇺🇿 O\'zbek', 'ru': '🇷🇺 Rus', 'en': '🏴󠁧󠁢󠁥󠁮󠁧󠁿 Ingliz'}
    lang_line = "  ".join(
        f"{lang_map.get(k, k)}: <b>{v}</b>"
        for k, v in d['lang_stats'].items()
    ) or "—"

    # Cancel rate
    total_closed = (d['finished_orders'] or 0) + (d['cancelled_orders'] or 0)
    cancel_rate = round((d['cancelled_orders'] / total_closed) * 100, 1) if total_closed > 0 else 0
    finish_rate = round((d['finished_orders'] / total_closed) * 100, 1) if total_closed > 0 else 0

    # Groups list
    groups_text = ""
    for g in d['groups_list'][:10]:  # Max 10 ta ko'rsatish
        chat_id, title, is_order, is_parcel = g
        flags = []
        if is_order: flags.append("🚕")
        if is_parcel: flags.append("📦")
        flag_str = " ".join(flags) if flags else "❌"
        safe_title = (title or str(chat_id))[:30]
        groups_text += f"  {flag_str} <code>{safe_title}</code>\n"
    if not groups_text:
        groups_text = "  — Hali guruh yo'q\n"

    # Channels list
    channels_text = ""
    for ch in d['channels_list'][:5]:
        ch_id, link, is_active = ch
        status = "✅" if is_active else "❌"
        ch_label = link if link else str(ch_id)
        channels_text += f"  {status} <code>{ch_label[:35]}</code>\n"
    if not channels_text:
        channels_text = "  — Hali kanal yo'q\n"

    text = (
        f"🔍 <b>BOTNING TO'LIQ 360° TAHLILI</b>\n"
        f"🕐 <i>{now}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"👥 <b>FOYDALANUVCHILAR</b>\n"
        f"  📲 Botga kirganlar:      <b>{d['total_starters']:,}</b> ta\n"
        f"  ✅ Ro'yxatdan o'tganlar: <b>{d['total_registered']:,}</b> ta\n"
        f"  👤 Yo'lovchilar:         <b>{d['total_passengers']:,}</b> ta\n"
        f"  🚗 Haydovchilar:         <b>{d['total_drivers']:,}</b> ta\n"
        f"  🚫 Bloklangan:           <b>{d['blocked_users']:,}</b> ta\n"
        f"  🌐 Til bo'yicha: {lang_line}\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚕 <b>HAYDOVCHILAR</b>\n"
        f"  ✅ Tasdiqlangan:   <b>{d['approved_drivers']}</b> ta\n"
        f"  🟢 Hozir online:  <b>{d['online_drivers']}</b> ta\n"
        f"  ✨ Comfort sinfi: <b>{d['comfort_drivers']}</b> ta\n"
        f"  ⭐ O'rtacha reyting: <b>{d['avg_driver_rating']:.1f}/5.0</b>\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 <b>BUYURTMALAR</b>\n"
        f"  📦 Jami:            <b>{d['total_orders']:,}</b> ta\n"
        f"  🚕 Taksi:          <b>{d['taxi_orders']:,}</b> ta\n"
        f"  📫 Pochta:         <b>{d['parcel_orders']:,}</b> ta\n"
        f"  🔄 Hozir faol:     <b>{d['active_orders']}</b> ta\n"
        f"  ✅ Yakunlangan:    <b>{d['finished_orders']:,}</b> ta ({finish_rate}%)\n"
        f"  ❌ Bekor qilingan: <b>{d['cancelled_orders']:,}</b> ta ({cancel_rate}%)\n"
        f"  💰 Umumiy aylanma: <b>{int(d['total_turnover']):,}</b> so'm\n"
        f"  📊 O'rtacha narx:  <b>{int(d['avg_order_price']):,}</b> so'm\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 <b>MOLIYA</b>\n"
        f"  💰 Jami hamyon balansi: <b>{int(d['total_balance']):,}</b> so'm\n"
        f"  🎁 Jami cashback:       <b>{int(d['total_cashback']):,}</b> so'm\n"
        f"  💺 Faol reyslar:        <b>{d['active_rides']}</b> ta\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 <b>GURUHLAR ({d['total_groups']} ta)</b>\n"
        f"  🚕 Taksi guruhlari: <b>{d['order_groups_count']}</b> ta\n"
        f"  📦 Pochta guruhlari: <b>{d['parcel_groups_count']}</b> ta\n"
        f"{groups_text}"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 <b>KANALLAR ({d['total_channels']} ta)</b>\n"
        f"  ✅ Faol kanallar: <b>{d['active_channels_count']}</b> ta\n"
        f"{channels_text}"
        f"━━━━━━━━━━━━━━━━━━━━━━━"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="stats_deep_audit"),
         InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_stats")]
    ])
    try:
        if msg:
            await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        # If too long, send as two messages
        half = len(text) // 2
        split_at = text.rfind("\n", 0, half)
        await callback.message.answer(text[:split_at], parse_mode="HTML")
        await callback.message.answer(text[split_at:], reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("stats_"), admin_filter)
async def show_stats(callback: types.CallbackQuery):
    await callback.answer()
    period = callback.data.split("_")[1]
    stats = await get_detailed_stats(period)
    
    text = (
        f"📊 <b>STATISTIKA ({period.upper()})</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 Umumiy aylanma: <code>{stats['revenue']:,}</code> s\n"
        f"📈 Sof foyda: <code>{stats['profit']:,}</code> s\n"
        f"✅ Tugatilgan: {stats['finished']} ta\n"
        f"❌ Bekor qilingan: {stats['cancelled']} ta\n"
        f"👥 Yangi userlar ({period}): {stats['new_users']} ta\n"
        f"👥 Jami userlar (Botga kirganlar): <b>{stats['total_users']} ta</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"💸 Kutilayotgan yechimlar: <b>{stats['withdraw_pending']} ta</b>\n"
        f"💰 Jami yechilgan: <code>{stats['withdraw_total']:,}</code> s\n"
        f"━━━━━━━━━━━━━━\n"
        f"💬 Guruhlar soni: <b>{stats['groups_count']} ta</b>\n"
        f"📢 Kanallar soni: <b>{stats['channels_count']} ta</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_stats")]])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        pass

@router.callback_query(F.data == "adm_reports", admin_filter)
async def reports_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Sana bo'yicha", callback_data="rp_date")],
        [InlineKeyboardButton(text="🚗 Haydovchilar", callback_data="rp_role_driver"),
         InlineKeyboardButton(text="👤 Yo'lovchilar", callback_data="rp_role_passenger")],
        [InlineKeyboardButton(text="🔍 User ID bo'yicha", callback_data="rp_user")],
        [InlineKeyboardButton(text="📥 To'liq baza (Excel)", callback_data="export_excel"),
         InlineKeyboardButton(text="📝 Statistika (Word)", callback_data="export_word")],
        [InlineKeyboardButton(text="🆔 Barcha User ID (Word)", callback_data="export_starters")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")]
    ])
    try:
        await callback.message.edit_text(
            "📊 <b>HISOBOTLAR MARKAZI</b>\n\n"
            "Qaysi turda hisobot olmoqchisiz?",
            reply_markup=kb, parse_mode="HTML"
        )
    except:
        pass

@router.callback_query(F.data == "rp_date", admin_filter)
async def rp_date_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_report_date)
    await callback.message.edit_text(
        "📅 <b>Sana yoki davrni kiriting:</b>\n\n"
        "📌 Kunlik: <code>2024-04-18</code>\n"
        "📌 Oylik:  <code>2024-04</code>\n"
        "📌 Yillik: <code>2024</code>\n"
        "📌 Bugun:  <code>bugun</code>\n\n"
        "<i>Kiritish formati muhim!</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor", callback_data="adm_reports")]
        ])
    )

@router.message(AdminStates.waiting_for_report_date, admin_filter)
async def rp_date_process(message: types.Message, state: FSMContext):
    from utils.reports import parse_date_input, generate_date_report_excel
    
    start, end, label = parse_date_input(message.text)
    if not start:
        return await message.answer(
            "❌ <b>Format noto'g'ri!</b>\n\n"
            "To'g'ri formatlar:\n• Kun: 2024-04-18\n• Oy: 2024-04\n• Yil: 2024\n• Bugun: bugun",
            parse_mode="HTML"
        )
    
    wait_msg = await message.answer(f"⏳ <b>{label}</b> uchun hisobot tayyorlanmoqda...", parse_mode="HTML")
    path = f"date_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    try:
        await generate_date_report_excel(path, start, end, label)
        await wait_msg.delete()
        await message.answer_document(FSInputFile(path), caption=f"✅ <b>Hisobot tayyor!</b>\n📅 Davr: {label}", parse_mode="HTML")
        os.remove(path)
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {e}")
    await state.clear()

@router.callback_query(F.data.startswith("rp_role_"), admin_filter)
async def rp_role_report(callback: types.CallbackQuery):
    from utils.reports import generate_role_report_excel
    role = callback.data.replace("rp_role_", "")
    label = "Haydovchilar" if role == "driver" else "Yo'lovchilar"
    wait_msg = await callback.message.answer(f"⏳ <b>{label}</b> hisoboti tayyorlanmoqda...", parse_mode="HTML")
    await callback.answer()
    path = f"{role}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    try:
        await generate_role_report_excel(path, role)
        await wait_msg.delete()
        await callback.message.answer_document(FSInputFile(path), caption=f"✅ <b>{label} hisoboti tayyor!</b>", parse_mode="HTML")
        os.remove(path)
    except Exception as e:
        await callback.message.answer(f"❌ Xatolik: {e}")

@router.callback_query(F.data == "rp_user", admin_filter)
async def rp_user_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_report_user_id)
    await callback.message.edit_text(
        "🔍 <b>Foydalanuvchi ID sini kiriting:</b>\n\n(Foydalanuvchining Telegram ID-si)\n\n"
        "<i>ID ni 'Foydalanuvchilar' bo'limidan qidirib topishingiz mumkin.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor", callback_data="adm_reports")]])
    )

@router.message(AdminStates.waiting_for_report_user_id, admin_filter)
async def rp_user_process(message: types.Message, state: FSMContext):
    from utils.reports import generate_user_report_excel
    try:
        user_id = int(message.text.strip())
    except:
        return await message.answer("❌ Iltimos, faqat raqam kiriting (User ID).")
    
    wait_msg = await message.answer(f"⏳ ID <code>{user_id}</code> uchun hisobot tayyorlanmoqda...", parse_mode="HTML")
    path = f"user_{user_id}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    try:
        result = await generate_user_report_excel(path, user_id)
        if not result:
            await wait_msg.edit_text("❌ Bunday ID li foydalanuvchi topilmadi.")
        else:
            await wait_msg.delete()
            user_data, _, _, _ = await get_user_full_report(user_id)
            
            import html
            name = html.escape(user_data[1]) if user_data else f"ID: {user_id}"
            
            await message.answer_document(FSInputFile(path), caption=f"✅ <b>Foydalanuvchi hisoboti tayyor!</b>\n👤 {name}\n🆔 <code>{user_id}</code>", parse_mode="HTML")
        if os.path.exists(path): os.remove(path)
    except Exception as e:
        await wait_msg.edit_text(f"❌ Xatolik: {e}")
    await state.clear()

@router.callback_query(F.data.startswith("export_"), admin_filter)
async def handle_export(callback: types.CallbackQuery):
    format_type = callback.data.split("_")[1]
    await callback.answer("⏳ Fayl tayyorlanmoqda...")
    from utils.reports import generate_excel_report, generate_word_report
    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    path = f"{filename}.xlsx" if format_type == "excel" else f"{filename}.docx"
    if format_type == "excel": await generate_excel_report(path)
    elif format_type == "word": await generate_word_report(path)
    elif format_type == "starters":
        from utils.reports import generate_starters_report_word
        await generate_starters_report_word(path)
        format_type = "ID"
    else: return await callback.answer("Noma'lum format")
        
    if os.path.exists(path):
        await callback.message.answer_document(FSInputFile(path), caption=f"✅ {format_type.upper()} hisobot tayyor!")
        os.remove(path)
    else:
        await callback.answer("❌ Xatolik yuz berdi.", show_alert=True)
