from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import (
    get_user, get_user_status_counts, get_all_user_ids, update_user_status,
    search_users, update_user_balance, get_unapproved_drivers, approve_driver,
    get_top_drivers, reset_all_ratings_db, delete_user, db_session
)
from utils.states import AdminStates
from .base import admin_filter
import asyncio

router = Router()

@router.callback_query(F.data == "adm_users", admin_filter)
async def users_menu(callback: types.CallbackQuery):
    await callback.answer()
    from database.db import db_session
    stats = await get_user_status_counts()

    async with db_session() as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_registered = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM users WHERE role='driver'") as c:
            drivers = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM users WHERE role='passenger'") as c:
            passengers = (await c.fetchone())[0] or 0
        async with db.execute("SELECT language, COUNT(*) FROM users GROUP BY language") as c:
            lang_rows = await c.fetchall()
        async with db.execute("SELECT SUM(balance) FROM users") as c:
            total_bal = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM users WHERE status='blocked'") as c:
            blocked_cnt = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM drivers WHERE is_online=1") as c:
            online_drv = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM drivers WHERE is_approved=1") as c:
            approved_drv = (await c.fetchone())[0] or 0

    lang_map = {'uz': '🇺🇿', 'ru': '🇷🇺', 'en': '🇬🇧'}
    lang_line = "  ".join(f"{lang_map.get(k,'🌐')} {v} ta" for k, v in lang_rows) or "—"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Foydalanuvchi qidirish", callback_data="user_search")],
        [
            InlineKeyboardButton(text="🚗 Haydovchilar ro'yxati", callback_data="adm_list_drivers"),
            InlineKeyboardButton(text="👤 Yo'lovchilar ro'yxati", callback_data="adm_list_passengers"),
        ],
        [InlineKeyboardButton(text="🔄 Barcha statuslarni yangilash", callback_data="adm_sync_status")],
        [InlineKeyboardButton(text="🗑 Bloklaganlarni o'chirish", callback_data="adm_del_blocked")],
        [InlineKeyboardButton(text="📁 Barcha ID larni yuklab olish", callback_data="adm_export_ids")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")]
    ])

    text = (
        f"👥 <b>FOYDALANUVCHILAR — 100% TAHLIL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Ro'yxatdan o'tganlar:  <b>{total_registered:,}</b> ta\n"
        f"🚗 Haydovchilar:           <b>{drivers:,}</b> ta\n"
        f"  ✅ Tasdiqlangan:         <b>{approved_drv}</b> ta\n"
        f"  🟢 Hozir online:        <b>{online_drv}</b> ta\n"
        f"👤 Yo'lovchilar:           <b>{passengers:,}</b> ta\n"
        f"🚫 Bloklangan:            <b>{blocked_cnt:,}</b> ta\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 Til: {lang_line}\n"
        f"💰 Jami hamyon: <b>{int(total_bal):,}</b> so'm\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm_list_drivers", admin_filter)
async def adm_list_drivers(callback: types.CallbackQuery):
    await callback.answer()
    from database.db import db_session
    async with db_session() as db:
        async with db.execute(
            "SELECT u.user_id, u.full_name, u.phone, d.car_name, d.car_number, d.is_online, d.is_approved, d.rating "
            "FROM users u JOIN drivers d ON u.user_id=d.user_id ORDER BY d.is_online DESC, u.user_id DESC LIMIT 30"
        ) as c:
            rows = await c.fetchall()

    if not rows:
        return await callback.answer("Haydovchilar topilmadi.", show_alert=True)

    text = f"🚗 <b>HAYDOVCHILAR RO'YXATI (oxirgi 30 ta)</b>\n━━━━━━━━━━━━━━\n\n"
    for uid, name, phone, car, plate, is_online, is_approved, rating in rows:
        status = "🟢" if is_online else "🔴"
        appr = "✅" if is_approved else "⏳"
        text += (
            f"{status} {appr} <b>{name}</b> | {car} {plate}\n"
            f"  📞 {phone} | ⭐ {rating or 5.0:.1f} | <code>{uid}</code>\n"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_users")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm_list_passengers", admin_filter)
async def adm_list_passengers(callback: types.CallbackQuery):
    await callback.answer()
    from database.db import db_session
    async with db_session() as db:
        async with db.execute(
            "SELECT user_id, full_name, phone, balance, language, status "
            "FROM users WHERE role='passenger' ORDER BY user_id DESC LIMIT 30"
        ) as c:
            rows = await c.fetchall()

    if not rows:
        return await callback.answer("Yo'lovchilar topilmadi.", show_alert=True)

    text = f"👤 <b>YO'LOVCHILAR RO'YXATI (oxirgi 30 ta)</b>\n━━━━━━━━━━━━━━\n\n"
    for uid, name, phone, bal, lang, status in rows:
        st = "🚫" if status == 'blocked' else "✅"
        lang_flag = {'uz': '🇺🇿', 'ru': '🇷🇺', 'en': '🇬🇧'}.get(lang, '🌐')
        text += (
            f"{st} {lang_flag} <b>{name}</b>\n"
            f"  📞 {phone} | 💰 {int(bal or 0):,} so'm | <code>{uid}</code>\n"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_users")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm_sync_status", admin_filter)
async def adm_sync_status_handler(callback: types.CallbackQuery, bot: Bot):
    await callback.answer("⏳ Tekshirish boshlandi. Bu biroz vaqt olishi mumkin...", show_alert=True)
    user_ids = await get_all_user_ids()
    total = len(user_ids)
    active, blocked = 0, 0
    progress_msg = await callback.message.answer(f"🔄 Tekshirilmoqda: 0/{total}")
    
    for i, user_id in enumerate(user_ids):
        try:
            await bot.send_chat_action(user_id, "typing")
            await update_user_status(user_id, "active")
            active += 1
        except Exception:
            await update_user_status(user_id, "blocked")
            blocked += 1
        if (i + 1) % 20 == 0:
            try: await progress_msg.edit_text(f"🔄 Tekshirilmoqda: {i+1}/{total}\n✅ Faol: {active}\n❌ Blok: {blocked}")
            except: pass
            await asyncio.sleep(0.5)
            
    try:
        await progress_msg.edit_text(f"✅ <b>Tekshirish yakunlandi!</b>\n\n Jami: {total}\n✅ Faol: {active}\n❌ Bloklangan: {blocked}", parse_mode="HTML")
    except Exception:
        pass
    await users_menu(callback)

@router.callback_query(F.data == "adm_del_blocked", admin_filter)
async def adm_del_blocked_handler(callback: types.CallbackQuery):
    from database.db import delete_blocked_users
    deleted_count = await delete_blocked_users()
    await callback.answer(f"✅ {deleted_count} ta bloklagan foydalanuvchi bazadan o'chirildi!", show_alert=True)
    await users_menu(callback)

@router.callback_query(F.data == "adm_export_ids", admin_filter)
async def adm_export_ids_handler(callback: types.CallbackQuery, bot: Bot):
    await callback.answer("⏳ Yuklanmoqda...")
    user_ids = await get_all_user_ids()
    
    if not user_ids:
        return await callback.message.answer("❌ Foydalanuvchilar topilmadi.")
        
    # Write to a temporary file
    import os
    file_path = f"users_ids_{len(user_ids)}.txt"
    with open(file_path, "w") as f:
        f.write("\n".join(map(str, user_ids)))
        
    try:
        from aiogram.types import FSInputFile
        doc = FSInputFile(file_path)
        await bot.send_document(
            chat_id=callback.from_user.id, 
            document=doc, 
            caption=f"📁 <b>Barcha botga start bosgan foydalanuvchilar (ID)</b>\n\nJami: <b>{len(user_ids)}</b> ta",
            parse_mode="HTML"
        )
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@router.callback_query(F.data == "user_search", admin_filter)
async def user_search_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.searching_user)
    try:
        await callback.message.edit_text("🔍 ID, tel yoki ismni kiriting:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_users")]]))
    except:
        pass

@router.message(AdminStates.searching_user, F.text, admin_filter)
async def process_user_search(message: types.Message, state: FSMContext):
    results = await search_users(message.text)
    if not results:
        return await message.answer("❌ Topilmadi.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_users")]]))
    kb = [[InlineKeyboardButton(text=f"👤 {u[1]} ({u[2]})", callback_data=f"uv_{u[0]}")] for u in results[:10]]
    kb.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_users")])
    await message.answer(f"🔍 Natijalar: {len(results)} ta.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.clear()

@router.callback_query(F.data.startswith("uv_"), admin_filter)
async def view_user(callback: types.CallbackQuery):
    u_id = int(callback.data.split("_")[1])
    u = await get_user(u_id)
    if not u: return await callback.answer("Topilmadi.")
    import html
    safe_name = html.escape(u[1])
    text = (
        f"👤 <b>PROFIL</b>\n\nID: <code>{u[0]}</code>\nF.I.SH: {safe_name}\nTel: {u[2]}\n"
        f"Rol: {u[4]}\nHolat: {u[5]}\n💰 Balans: {u[6]:,} s\n📅 Reg: {u[9]}"
    )
    kb = [
        [InlineKeyboardButton(text="💬 Xabar yuborish", callback_data=f"usermsg_{u[0]}")],
        [InlineKeyboardButton(text="💰 Balans", callback_data=f"ubal_{u[0]}")],
        [InlineKeyboardButton(text="❌ O'chirish", callback_data=f"udel_{u[0]}")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_users")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")


@router.callback_query(F.data.startswith("ubal_"), admin_filter)
async def admin_change_bal_start(callback: types.CallbackQuery, state: FSMContext):
    u_id = int(callback.data.split("_")[1])
    await state.update_data(target_user_id=u_id)
    await state.set_state(AdminStates.entering_deposit_amount)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"uv_{u_id}")]])
    try:
        await callback.message.edit_text(f"💰 <b>Balansni o'zgartirish</b>\n\nID: <code>{u_id}</code>\n\nMasalan: <code>50000</code> yoki <code>-10000</code>", reply_markup=kb, parse_mode="HTML")
    except:
        pass

@router.message(AdminStates.entering_deposit_amount, F.text, admin_filter)
async def admin_change_bal_process(message: types.Message, state: FSMContext):
    data = await state.get_data()
    u_id = data.get('target_user_id')
    if not u_id: return await state.clear()
    try: amount = float(message.text.strip())
    except: return await message.answer("❌ Iltimos, faqat raqam kiriting!")
    await update_user_balance(u_id, amount, "Admin tomonidan tahrirlandi", "in" if amount > 0 else "out")
    await message.answer(f"✅ Balans o'zgartirildi: {amount:,.0f} so'm")
    await state.clear()

@router.callback_query(F.data.startswith("udel_"), admin_filter)
async def admin_delete_user(callback: types.CallbackQuery):
    u_id = int(callback.data.split("_")[1])
    await delete_user(u_id)
    await callback.answer("✅ Foydalanuvchi o'chirildi!", show_alert=True)
    await users_menu(callback)

@router.callback_query(F.data.startswith("usermsg_"), admin_filter)
async def admin_msg_user_start(callback: types.CallbackQuery, state: FSMContext):
    u_id = int(callback.data.split("_")[1])
    await state.update_data(target_user_id=u_id)
    await state.set_state(AdminStates.waiting_for_admin_msg)
    try:
        await callback.message.edit_text(f"💬 <b>Xabar yuborish</b>\nID: <code>{u_id}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"uv_{u_id}")]]), parse_mode="HTML")
    except:
        pass

@router.message(AdminStates.waiting_for_admin_msg, admin_filter)
async def admin_msg_user_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    u_id = data.get('target_user_id')
    try:
        await message.bot.send_message(u_id, f"🔔 <b>Administratordan xabar keldi:</b>\n━━━━━━━━━━━━━━\n\n{message.text}", parse_mode="HTML")
        await message.answer("✅ Xabar yuborildi!")
    except: await message.answer("❌ Xabar yuborilmadi (User botni bloklagan bo'lishi mumkin).")
    await state.clear()

@router.callback_query(F.data == "adm_drivers", admin_filter)
async def drivers_menu(callback: types.CallbackQuery):
    await callback.answer()
    unapproved = await get_unapproved_drivers()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⏳ Tasdiqlash ({len(unapproved)})", callback_data="dr_unapproved")],
        [InlineKeyboardButton(text="➕ Haydovchi qo'shish (ID)", callback_data="adm_add_driver_id")],
        [InlineKeyboardButton(text="🟢 Onlayn", callback_data="dr_online"), InlineKeyboardButton(text="🔴 Offlayn", callback_data="dr_offline")],
        [InlineKeyboardButton(text="⭐ Reyting", callback_data="dr_ratings")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")]
    ])
    await callback.message.edit_text("🚗 <b>Haydovchilar:</b>", reply_markup=kb, parse_mode="HTML")

# --- Manual Driver Addition ---

@router.callback_query(F.data == "adm_add_driver_id", admin_filter)
async def adm_add_driver_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.adding_driver_id)
    await callback.message.edit_text(
        "🆔 <b>Foydalanuvchi ID sini kiriting:</b>\n\n"
        "<i>Eslatma: Foydalanuvchi avval botdan ro'yxatdan o'tgan bo'lishi kerak.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_drivers")]]),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminStates.adding_driver_id, admin_filter)
async def adm_add_driver_id_process(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Iltimos, faqat raqamli ID kiriting!")
    
    target_id = int(message.text)
    user = await get_user(target_id)
    
    if not user:
        return await message.answer("❌ Ushbu ID bo'yicha foydalanuvchi topilmadi. U avval botni boshlagan bo'lishi shart.")

    await state.update_data(m_driver_id=target_id)
    await state.set_state(AdminStates.adding_driver_car_name)
    await message.answer(f"👤 <b>Foydalanuvchi:</b> {user[1]}\n\n🚗 <b>Mashina rusumini kiriting:</b> (masalan: Cobalt)", parse_mode="HTML")

@router.message(AdminStates.adding_driver_car_name, admin_filter)
async def adm_add_driver_car_name(message: types.Message, state: FSMContext):
    await state.update_data(m_car_name=message.text)
    await state.set_state(AdminStates.adding_driver_car_number)
    await message.answer("🔢 <b>Mashina raqamini kiriting:</b> (masalan: 01A777AA)", parse_mode="HTML")

@router.message(AdminStates.adding_driver_car_number, admin_filter)
async def adm_add_driver_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get('m_driver_id')
    car_name = data.get('m_car_name')
    car_number = message.text.upper()
    
    from database.db import add_driver_details, update_user_status
    # 1. Add driver details and approve immediately
    await add_driver_details(target_id, car_name, car_number, is_approved=1)
    # 2. Set role to driver if not already
    async with db_session() as db:
        await db.execute("UPDATE users SET role = 'driver' WHERE user_id = ?", (target_id,))
        await db.commit()
        
    await message.answer(f"✅ <b>Haydovchi muvaffaqiyatli qo'shildi!</b>\n\nID: {target_id}\nIsm: {car_name}\nRaqam: {car_number}", parse_mode="HTML")
    try:
        await message.bot.send_message(target_id, "🎉 <b>Tabriklaymiz!</b>\nAdmin sizni haydovchi sifatida ro'yxatdan o'tkazdi va profilingiz tasdiqlandi. Endi buyurtmalarni qabul qilishingiz mumkin.")
    except:
        pass
    await state.clear()
    await message.answer("🔙 Haydovchilar menyusiga qaytish uchun quyidagi tugmani bosing:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                             [InlineKeyboardButton(text="🚗 Haydovchilar", callback_data="adm_drivers")]
                         ]))

@router.callback_query(F.data == "dr_unapproved", admin_filter)
async def dr_unapproved_list(callback: types.CallbackQuery):
    records = await get_unapproved_drivers()
    if not records: return await callback.answer("Hozircha yo'q.")
    text = "⏳ <b>Kutilmoqda:</b>\n\n"
    kb = [[InlineKeyboardButton(text=f"✅ {d[1]}", callback_data=f"drapp_{d[0]}")] for d in records[:10]]
    kb.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_drivers")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data.startswith("drapp_"), admin_filter)
@router.callback_query(F.data.startswith("adm_drv_app_"), admin_filter)
async def drapp_process(callback: types.CallbackQuery):
    u_id = int(callback.data.split("_")[-1])
    await approve_driver(u_id)
    try: await callback.bot.send_message(u_id, "✅ Profilingiz tasdiqlandi!")
    except: pass
    await callback.answer("Tasdiqlandi.")
    # If it was from the unapproved list, refresh the list
    if callback.data.startswith("drapp_"):
        await dr_unapproved_list(callback)
    else:
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ <b>TASDIQLANDI</b>", parse_mode="HTML")

@router.callback_query(F.data.startswith("adm_drv_rej_"), admin_filter)
async def dr_reject_process(callback: types.CallbackQuery):
    u_id = int(callback.data.split("_")[-1])
    try: await callback.bot.send_message(u_id, "❌ Kechirasiz, profilingiz admin tomonidan rad etildi. Iltimos ma'lumotlarni tekshirib qaytadan yuboring.")
    except: pass
    await callback.answer("Rad etildi.")
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ <b>RAD ETILDI</b>", parse_mode="HTML")

@router.callback_query(F.data == "dr_ratings", admin_filter)
async def dr_ratings_list(callback: types.CallbackQuery):
    top_drivers = await get_top_drivers(limit=20)
    if not top_drivers: return await callback.answer("Reytinglar mavjud emas.")
    import html
    text = f"🏆 <b>TOP HAYDOVCHILAR:</b>\n━━━━━━━━━━━━━━\n\n"  # ← text initialized here
    for d in top_drivers: 
        safe_name = html.escape(d[0])
        text += f"👤 <b>{safe_name}</b>\n└ ⭐ {d[2]:.1f} | 🏁 {d[3]} ta safar\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛑 Reytinglarni nolga tushirish", callback_data="confirm_reset_ratings")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_drivers")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "confirm_reset_ratings", admin_filter)
async def confirm_reset_ratings_handler(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ha, hammasini o'chirish", callback_data="reset_ratings_confirmed")],
        [InlineKeyboardButton(text="❌ Yo'q, bekor qilish", callback_data="dr_ratings")]
    ])
    await callback.message.edit_text("⚠️ <b>DIQQAT!</b>\n\nReytinglarni o'chirishni tasdiqlaysizmi?", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "reset_ratings_confirmed", admin_filter)
async def reset_ratings_confirmed_handler(callback: types.CallbackQuery):
    await reset_all_ratings_db()
    await callback.answer("✅ Reytinglar tozalandi.")
    await dr_ratings_list(callback)

@router.callback_query(F.data.in_({"dr_online", "dr_offline"}), admin_filter)
async def dr_status_list(callback: types.CallbackQuery):
    is_online = callback.data == "dr_online"
    from database.db import get_drivers_by_status
    drivers = await get_drivers_by_status(is_online)
    
    status_label = "🟢 ONLAYN" if is_online else "🔴 OFFLAYN"
    if not drivers:
        return await callback.answer(f"Hozircha {status_label} haydovchilar yo'q.", show_alert=True)
        
    await callback.answer()
    text = f"🚗 <b>{status_label} HAYDOVCHILAR:</b>\n━━━━━━━━━━━━━━\n\n"
    import html
    kb = []
    for d in drivers[:20]:
        # d indices: 0:id, 1:name, 2:phone, 3:car, 4:number, 5:rating, 6:rides
        safe_name = html.escape(d[1])
        text += f"👤 <b>{safe_name}</b> | 📞 {d[2]}\n🚗 {d[3]} ({d[4]})\n⭐ {d[5]:.1f} | 🏁 {d[6]} ta safar\n\n"
        kb.append([InlineKeyboardButton(text=f"👁 {d[1]}", callback_data=f"uv_{d[0]}")])
        
    kb.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_drivers")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
