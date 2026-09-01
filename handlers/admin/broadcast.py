from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_all_user_ids, get_all_groups, get_user_ids_by_role
from utils.states import AdminStates
from .base import admin_filter, get_admin_main_kb
import asyncio
import logging

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "adm_broadcast", admin_filter)
async def broadcast_menu(callback: types.CallbackQuery):
    await callback.answer()
    from database.db import db_session
    async with db_session() as db:
        # Barcha unikal foydalanuvchilar: bot_starters + users (birlashtirilgan)
        async with db.execute(
            "SELECT COUNT(*) FROM (SELECT user_id FROM users UNION SELECT user_id FROM bot_starters)"
        ) as c:
            total_all = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM users WHERE role='driver'") as c:
            total_drivers = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM users WHERE role='passenger'") as c:
            total_passengers = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM groups") as c:
            total_groups = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_registered = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM bot_starters") as c:
            total_starters = (await c.fetchone())[0] or 0

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"👥 HAMMAGA yuborish ({total_all:,} ta)",
            callback_data="bc_all"
        )],
        [
            InlineKeyboardButton(text=f"🚗 Haydovchilar ({total_drivers})", callback_data="bc_driver"),
            InlineKeyboardButton(text=f"👤 Yo'lovchilar ({total_passengers})", callback_data="bc_passenger"),
        ],
        [InlineKeyboardButton(text=f"💬 Guruhlarga ({total_groups} ta)", callback_data="bc_groups")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")]
    ])
    await callback.message.edit_text(
        f"📢 <b>REKLAMA / XABAR YUBORISH</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"📲 Start bosganlar:       <b>{total_starters:,}</b> ta\n"
        f"✅ Ro'yxatdan o'tganlar: <b>{total_registered:,}</b> ta\n"
        f"📊 Hammasi (unikal):     <b>{total_all:,}</b> ta\n"
        f"💬 Guruhlar:             <b>{total_groups}</b> ta\n\n"
        f"<i>Kimga yuboramiz?</i>",
        reply_markup=kb, parse_mode="HTML"
    )


@router.callback_query(F.data.in_({"bc_all", "bc_driver", "bc_passenger", "bc_groups"}), admin_filter)
async def bc_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    target = callback.data.split("_")[1]
    labels = {
        'all': "👥 Barcha foydalanuvchilar",
        'driver': "🚗 Haydovchilar",
        'passenger': "👤 Yo'lovchilar",
        'groups': "💬 Guruhlar"
    }
    await state.update_data(target=target)
    await state.set_state(AdminStates.waiting_for_ad_content)
    await callback.message.edit_text(
        f"📝 <b>{labels.get(target, target)}</b> uchun xabar yozing yoki yuboring:\n\n"
        f"<i>(matn, rasm, video, fayl — barchasi qabul qilinadi)</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_broadcast")]
        ]),
        parse_mode="HTML"
    )


@router.message(AdminStates.waiting_for_ad_content, admin_filter)
async def bc_process_content(message: types.Message, state: FSMContext):
    await state.update_data(ad_chat_id=message.chat.id, ad_message_id=message.message_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Tugma qo'shish", callback_data="bc_add_btn")],
        [InlineKeyboardButton(text="🚀 Tugmasiz — Hoziroq yuborish", callback_data="bc_send_now")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_broadcast")]
    ])
    await message.answer("✅ <b>Xabar qabul qilindi!</b>\n\nReklamaga inline tugma qo'shasizmi?", reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "bc_add_btn", admin_filter)
async def bc_add_btn_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_ad_button_text)
    await callback.message.answer("⌨️ <b>Tugma matni</b>ni kiriting (masalan: <i>Botga o'tish</i>):", parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_for_ad_button_text, admin_filter)
async def bc_btn_text(message: types.Message, state: FSMContext):
    await state.update_data(btn_text=message.text)
    await state.set_state(AdminStates.waiting_for_ad_button_url)
    await message.answer("🔗 <b>Tugma havolasini</b> (URL) kiriting:", parse_mode="HTML")


@router.message(AdminStates.waiting_for_ad_button_url, admin_filter)
async def bc_btn_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    if not (url.startswith("http") or url.startswith("tg://")):
        return await message.answer("❌ Iltimos, to'g'ri URL kiriting (http:// yoki tg:// bilan boshlash kerak).")
    await state.update_data(btn_url=url)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Tasdiqlash va yuborish", callback_data="bc_confirm_send")],
        [InlineKeyboardButton(text="❌ Bekor", callback_data="adm_broadcast")]
    ])
    await message.answer("✅ <b>Tayyor!</b> Yuborishni tasdiqlaysizmi?", reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "bc_send_now", admin_filter)
async def bc_send_now_callback(callback: types.CallbackQuery, state: FSMContext):
    await start_broadcast_task(callback.message, state, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "bc_confirm_send", admin_filter)
async def bc_confirm_callback(callback: types.CallbackQuery, state: FSMContext):
    await start_broadcast_task(callback.message, state, callback.from_user.id)
    await callback.answer()


async def start_broadcast_task(message: types.Message, state: FSMContext, admin_id: int):
    data = await state.get_data()
    target = data['target']
    ad_chat_id = data['ad_chat_id']
    ad_message_id = data['ad_message_id']
    btn_text = data.get('btn_text')
    btn_url = data.get('btn_url')
    await state.clear()
    asyncio.create_task(do_broadcast(message, admin_id, target, ad_chat_id, ad_message_id, btn_text, btn_url))


async def _get_all_recipient_ids(target: str) -> list:
    """Returns FULL list of recipient IDs.
    'all'  → bot_starters UNION users (hammasi — /start bosgan + ro'yxatdan o'tgan)
    """
    from database.db import db_session

    if target == 'groups':
        groups = await get_all_groups()
        return [g[0] for g in groups]

    if target in ('driver', 'passenger'):
        return await get_user_ids_by_role(target)

    # target == 'all': bot_starters + users — HAMMA kim /start bosgan
    async with db_session() as db:
        async with db.execute(
            "SELECT user_id FROM users UNION SELECT user_id FROM bot_starters"
        ) as c:
            rows = await c.fetchall()
    return [row[0] for row in rows]


async def do_broadcast(
    message: types.Message,
    admin_id: int,
    target: str,
    ad_chat_id: int,
    ad_message_id: int,
    btn_text: str = None,
    btn_url: str = None
):
    kb = None
    if btn_text and btn_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_text, url=btn_url)]])

    u_ids = await _get_all_recipient_ids(target)
    total = len(u_ids)

    if total == 0:
        await message.answer("⚠️ Reklama yuborish uchun foydalanuvchilar topilmadi.")
        return

    target_label = {
        'all': "Barcha foydalanuvchilar",
        'driver': "Haydovchilar",
        'passenger': "Yo'lovchilar",
        'groups': "Guruhlar"
    }.get(target, target)

    sent_msg = await message.answer(
        f"🚀 <b>{target_label}</b> ga yuborish boshlandi...\n"
        f"📊 Jami: <b>{total:,}</b> ta manzil\n\n"
        f"<i>Iltimos kuting...</i>",
        parse_mode="HTML"
    )

    sent, failed, blocked_count = 0, 0, 0
    sem = asyncio.Semaphore(25)

    async def send_to_one(uid: int):
        nonlocal sent, failed, blocked_count
        async with sem:
            try:
                await message.bot.copy_message(
                    chat_id=uid,
                    from_chat_id=ad_chat_id,
                    message_id=ad_message_id,
                    reply_markup=kb
                )
                sent += 1
            except Exception as e:
                err = str(e).lower()
                if any(x in err for x in ["blocked", "deactivated", "forbidden", "kicked", "not found", "chat not found"]):
                    blocked_count += 1
                else:
                    logger.warning(f"Broadcast error to {uid}: {e}")
                failed += 1

    tasks = [send_to_one(uid) for uid in u_ids]
    chunk_size = 100

    for i in range(0, len(tasks), chunk_size):
        await asyncio.gather(*tasks[i:i + chunk_size])
        done = min(i + chunk_size, total)
        pct = round((done / total) * 100)
        bar_filled = int(pct / 10)
        bar = "🟩" * bar_filled + "⬜" * (10 - bar_filled)
        try:
            await sent_msg.edit_text(
                f"📤 <b>Yuborilmoqda...</b>\n"
                f"{bar} {pct}%\n\n"
                f"✅ Yuborildi: <b>{sent:,}</b>\n"
                f"❌ Xatolik: <b>{failed:,}</b>\n"
                f"📊 {done:,}/{total:,}",
                parse_mode="HTML"
            )
        except Exception:
            pass
        await asyncio.sleep(0.3)

    # Final report
    success_rate = round((sent / total) * 100, 1) if total > 0 else 0
    from database.db import get_admin
    adm = await get_admin(admin_id)
    perms = adm[2] if adm else 'all'

    final_text = (
        f"✅ <b>REKLAMA YAKUNLANDI!</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎯 Maqsad: <b>{target_label}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"📊 Jami manzil:    <b>{total:,}</b> ta\n"
        f"✅ Yetkazildi:     <b>{sent:,}</b> ta\n"
        f"🚫 Bloklagan:      <b>{blocked_count:,}</b> ta\n"
        f"❌ Boshqa xatolik: <b>{failed - blocked_count:,}</b> ta\n"
        f"━━━━━━━━━━━━━━\n"
        f"📈 Yetkazish darajasi: <b>{success_rate}%</b>"
    )
    await message.answer(final_text, reply_markup=get_admin_main_kb(admin_id, perms), parse_mode="HTML")
    logger.info(f"Broadcast done: target={target}, total={total}, sent={sent}, failed={failed}")


@router.callback_query(F.data == "bc_cancel", admin_filter)
async def bc_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    from database.db import get_admin
    adm = await get_admin(callback.from_user.id)
    perms = adm[2] if adm else 'all'
    await callback.message.edit_text("❌ Reklama bekor qilindi.", reply_markup=get_admin_main_kb(callback.from_user.id, perms))
