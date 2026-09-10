from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from .base import admin_filter, get_admin_main_kb, get_admin_reply_kb
from utils.states import AdminStates
from . import stats, users, orders, broadcast, settings, withdrawals, promocodes, logs, materials, autoreply, admins

router = Router()

# Include sub-routers
router.include_router(stats.router)
router.include_router(users.router)
router.include_router(orders.router)
router.include_router(broadcast.router)
router.include_router(settings.router)
router.include_router(withdrawals.router)
router.include_router(promocodes.router)
router.include_router(logs.router)
router.include_router(materials.router)
router.include_router(autoreply.router)
router.include_router(admins.router)

# ─── Admin panel ochish (/panel, /admin, tugma) ──────────────────────────────

@router.message(Command("panel"), admin_filter, StateFilter('*'))
@router.message(Command("admin"), admin_filter, StateFilter('*'))
@router.message(F.chat.type == "private", F.text.in_({"🛠 Admin Panel", "🛠 Админ panel", "⚙️ Admin Panel"}), admin_filter, StateFilter('*'))
async def admin_panel(message: types.Message, state: FSMContext):
    await state.clear()
    from database.db import get_admin
    adm = await get_admin(message.from_user.id)
    perms = adm[2] if adm else 'all'

    # Pastdagi doimiy reply keyboard
    reply_kb = get_admin_reply_kb(message.from_user.id, perms)

    await message.answer(
        "<b>💎 CHIROQCHI TAKSI — ADMIN MARKAZI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Tizim holati: <b>Barqaror ✅</b>\n"
        "\n<i>Pastdagi menyu orqali bo'limni tanlang:</i>",
        reply_markup=reply_kb,
        parse_mode="HTML"
    )


# ─── Inline callback — 'adm_main' orqali asosiy panel (chuqur sahifalardan ortga) ─

@router.callback_query(F.data == "adm_main", admin_filter)
async def admin_main_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    from database.db import get_admin
    adm = await get_admin(callback.from_user.id)
    perms = adm[2] if adm else 'all'

    reply_kb = get_admin_reply_kb(callback.from_user.id, perms)

    try:
        await callback.message.edit_text(
            "<b>💎 ADMIN MARKAZI</b>\n━━━━━━━━━━━━━━\n"
            "<i>Pastdagi menyu orqali bo'limni tanlang:</i>",
            reply_markup=None,
            parse_mode="HTML"
        )
    except:
        pass
    await callback.message.answer(
        "✅ Admin menyusi yangilandi.",
        reply_markup=reply_kb
    )


# ─── Reply keyboard tugmalarini ushlash ───────────────────────────────────────

_MODULE_MAP = {
    "📊 Statistika":       "adm_stats",
    "👥 Foydalanuvchilar": "adm_users",
    "🚗 Haydovchilar":     "adm_drivers",
    "📦 Buyurtmalar":      "adm_orders",
    "📢 Reklama":          "adm_broadcast",
    "💬 Guruhlar":         "adm_groups",
    "📢 Kanallar":         "adm_channels",
    "💳 Moliya":           "adm_finance",
    "⚙️ Sozlamalar":       "adm_settings",
    "👑 Adminlar":         "adm_mgmt",
}

@router.message(F.chat.type == "private", F.text.in_(set(_MODULE_MAP.keys())), admin_filter, StateFilter('*'))
async def admin_reply_btn_handler(message: types.Message, state: FSMContext):
    """Pastdagi reply keyboard tugmachalarini inline callback sifatida yo'naltiradi."""
    await state.clear()
    cb_data = _MODULE_MAP.get(message.text)
    if not cb_data:
        return

    from database.db import get_admin
    adm = await get_admin(message.from_user.id)
    perms = adm[2] if adm else 'all'

    # Inline keyboard bilan modul sahifasini ochish
    inline_kb = get_admin_main_kb(message.from_user.id, perms)

    # Har bir modul uchun alohida handler-callback ni simulate qilamiz
    # (Foydalanuvchi xuddi inline tugma bosgandek ishlaydi)
    fake_cb_map = {
        "adm_stats":     stats.router,
        "adm_users":     users.router,
        "adm_orders":    orders.router,
        "adm_broadcast": broadcast.router,
        "adm_settings":  settings.router,
        "adm_finance":   withdrawals.router,
        "adm_groups":    None,  # inline handler shu faylda
        "adm_mgmt":      admins.router,
        "adm_drivers":   None,
    }

    # Inline tugma bilan yo'naltirish xabari yuboramiz
    module_labels = {
        "adm_stats":     "📊 Statistika & Hisobot",
        "adm_users":     "👥 Foydalanuvchilar",
        "adm_drivers":   "🚗 Haydovchilar markazi",
        "adm_orders":    "📦 Buyurtmalar nazorati",
        "adm_broadcast": "📢 Reklama & Xabarnoma",
        "adm_groups":    "💬 Buyurtma Guruhlari",
        "adm_channels":  "📢 Majburiy Kanallar",
        "adm_finance":   "💳 Moliya & Promokodlar",
        "adm_settings":  "⚙️ Tizim Sozlamalari",
        "adm_mgmt":      "👑 Adminlar boshqaruvi",
    }
    label = module_labels.get(cb_data, "Bo'lim")
    nav_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔓 {label} ni ochish", callback_data=cb_data)],
        [InlineKeyboardButton(text="🔙 Panel", callback_data="adm_main")]
    ])
    await message.answer(
        f"<b>{label}</b>\n━━━━━━━━━━━━━━\n<i>Yuklanyapti...</i>",
        reply_markup=nav_kb,
        parse_mode="HTML"
    )

# Add group management here since it's relatively small and shares many imports
# --- 👥 GURUH VA KANALLAR BOSHQARUVI ---

# ─────────────────────────────────────────────────────────────────
# 💬 BUYURTMA GURUHLARI sahifasi
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.in_({"adm_groups", "adm_groups_refresh"}), admin_filter)
async def adm_groups_page(callback: types.CallbackQuery):
    await callback.answer()
    from database.db import get_all_groups, get_setting

    groups = await get_all_groups()
    gb_enabled = await get_setting('group_broadcasting_enabled', '1')
    gb_status = "✅ YOQILGAN" if gb_enabled == '1' else "❌ O'CHIRILGAN"

    text = (
        "💬 <b>BUYURTMA GURUHLARI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📢 <b>Guruhlarga efir:</b> {gb_status}\n"
        f"💬 <b>Jami guruhlar:</b> {len(groups)} ta\n\n"
        "Guruhni o'chirish uchun 🗑 tugmasini bosing.\n"
        "Buyurtma turini almashtirish uchun taxi/parsel tugmalarini bosing."
    )

    rows = [
        [
            InlineKeyboardButton(text=f"📢 Efir: {gb_status}", callback_data="toggle_gb_global"),
        ]
    ]

    if groups:
        for g in groups[:15]:
            rows.append([
                InlineKeyboardButton(text="🚕✅" if g[3] == 1 else "🚕❌", callback_data=f"toggle_group_taxi_{g[0]}"),
                InlineKeyboardButton(text="📦✅" if g[4] == 1 else "📦❌", callback_data=f"toggle_group_parcel_{g[0]}"),
                InlineKeyboardButton(text=f"🗑 {g[1] or g[0]}", callback_data=f"del_group_{g[0]}")
            ])
    else:
        rows.append([InlineKeyboardButton(text="⚠️ Guruhlar yo'q", callback_data="none")])

    rows.append([InlineKeyboardButton(text="➕ Guruh qo'shish", callback_data="adm_add_group_manual")])
    rows.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")])

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    except:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────
# 📢 MAJBURIY KANALLAR sahifasi
# ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.in_({"adm_channels", "adm_sub", "adm_channels_refresh"}), admin_filter)
async def adm_channels_page(callback: types.CallbackQuery):
    await callback.answer()
    from database.db import get_active_channels, get_setting

    channels = await get_active_channels()
    sub_en = await get_setting('sub_enabled', '0')
    sub_icon = "✅ YOQILGAN" if sub_en == '1' else "❌ O'CHIRILGAN"

    text = (
        "📢 <b>MAJBURIY KANALLAR (Obuna)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🛡 <b>Majburiy obuna:</b> {sub_icon}\n"
        f"📢 <b>Jami kanallar:</b> {len(channels)} ta\n\n"
        "Kanalni o'chirish uchun 🗑 tugmasini bosing."
    )

    rows = [
        [
            InlineKeyboardButton(text=f"🛡 Obuna: {sub_icon}", callback_data="toggle_sub_global"),
        ]
    ]

    if channels:
        for ch in channels[:10]:
            rows.append([
                InlineKeyboardButton(text=f"🗑 {ch[1] or ch[0]}", callback_data=f"del_channel_{ch[0]}")
            ])
    else:
        rows.append([InlineKeyboardButton(text="⚠️ Kanallar yo'q", callback_data="none")])

    rows.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="ch_add")])
    rows.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")])

    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    except:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")


@router.callback_query(F.data == "toggle_sub_global", admin_filter)
async def toggle_sub_global_handler(callback: types.CallbackQuery):
    from database.db import get_setting, update_setting
    curr = await get_setting('sub_enabled', '0')
    new_val = '0' if curr == '1' else '1'
    await update_setting('sub_enabled', new_val)
    await callback.answer("Majburiy obuna holati o'zgartirildi.")
    await adm_channels_page(callback)


@router.callback_query(F.data == "toggle_gb_global", admin_filter)
async def toggle_gb_global_handler(callback: types.CallbackQuery):
    from database.db import get_setting, update_setting
    curr = await get_setting('group_broadcasting_enabled', '1')
    new_val = '0' if curr == '1' else '1'
    await update_setting('group_broadcasting_enabled', new_val)
    status_text = "yoqildi" if new_val == '1' else "o'chirildi"
    await callback.answer(f"Global efir {status_text}")
    await adm_groups_page(callback)


@router.callback_query(F.data.startswith("toggle_group_"), admin_filter)
async def toggle_group_type_handler(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    g_type = parts[2]
    g_id = parts[3]
    from database.db import toggle_group_order_channel, toggle_group_parcel_channel, get_all_groups
    
    groups = await get_all_groups()
    group = next((g for g in groups if str(g[0]) == str(g_id)), None)
    if not group: return await callback.answer("Guruh topilmadi.")
    
    if g_type == 'taxi':
        new_status = 0 if group[3] == 1 else 1
        await toggle_group_order_channel(g_id, new_status)
    else:
        new_status = 0 if group[4] == 1 else 1
        await toggle_group_parcel_channel(g_id, new_status)
        
    await callback.answer("O'zgartirildi.")
    await adm_groups_page(callback)


@router.callback_query(F.data.startswith("del_group_"), admin_filter)
async def del_group_handler(callback: types.CallbackQuery):
    g_id = callback.data.replace("del_group_", "")
    from database.db import delete_group
    await delete_group(g_id)
    await callback.answer("Guruh o'chirildi.")
    await adm_groups_page(callback)


@router.callback_query(F.data.startswith("del_channel_"), admin_filter)
async def del_channel_handler(callback: types.CallbackQuery):
    ch_id = callback.data.replace("del_channel_", "")
    from database.db import remove_channel
    await remove_channel(ch_id)
    await callback.answer("Kanal o'chirildi.")
    await adm_channels_page(callback)


@router.callback_query(F.data == "adm_add_group_manual", admin_filter)
async def adm_add_group_manual_handler(callback: types.CallbackQuery, state: FSMContext):
    from utils.states import AdminStates
    await state.set_state(AdminStates.adding_group_id)
    await callback.answer()
    text = (
        "➕ <b>Yangi guruh ulash:</b>\n"
        "━━━━━━━━━━━━━━\n"
        "Guruhni ulash uchun quyidagi usullardan birini tanlang:\n\n"
        "1️⃣ <b>Eng oson usul:</b> Guruhdan ixtiyoriy bitta xabarni ushbu botga <b>FORWARD (uzatish)</b> qiling!\n"
        "2️⃣ Guruh havolasini (<code>https://t.me/...</code>) yoki <b>@username</b>ini yuboring.\n"
        "3️⃣ Yoki guruhning <b>-100...</b> ID raqamini yozib yuboring.\n\n"
        "⚠️ <b>MUHIM:</b> Buyurtmalar yetib borishi uchun bot guruhda <b>Administrator</b> bo'lishi shart!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_groups")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except:
        pass


@router.message(AdminStates.adding_group_id, admin_filter)
async def process_add_group_id(message: types.Message, state: FSMContext):
    # 0. Check cancellation
    if message.text and (message.text.startswith("/") or message.text in ["🔙 Ortga", "❌ Bekor qilish"]):
        await state.clear()
        return

    chat_target = None

    # 1. Forwarded message from group or channel
    if message.forward_origin:
        f_type = getattr(message.forward_origin, 'type', None)
        if f_type in ('channel', 'chat'):
            chat_target = getattr(message.forward_origin, 'chat', None)
    elif message.forward_from_chat:
        chat_target = message.forward_from_chat

    target = None
    if chat_target:
        target = chat_target.id
    elif message.text:
        raw = message.text.strip()
        
        # Check for private invite links (+...)
        if "t.me/+" in raw or "t.me/joinchat/" in raw:
            await message.answer(
                "⚠️ <b>Yopiq (xususiy) havola kiritildi!</b>\n\n"
                "Telegram botlar yopiq havoladan guruh ID sini to'g'ridan-to'g'ri aniqlay olmaydi.\n\n"
                "👉 <b>Buning juda oson yo'li:</b>\n"
                "1. Botni o'sha guruhga <b>Administrator</b> qilib qo'shing.\n"
                "2. O'sha guruhdan bitta xabarni ushbu botga <b>FORWARD (uzatish)</b> qiling!\n"
                "Yoki guruhning <code>-100...</code> ID sini yuboring.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_groups")]
                ]),
                parse_mode="HTML"
            )
            return

        # Clean URL if provided
        if "t.me/" in raw:
            parts = raw.split("t.me/")[-1].split("/")
            if parts:
                raw = parts[0].split("?")[0]
        
        raw = raw.strip()
        if (raw.startswith("-") and raw[1:].isdigit()) or raw.isdigit():
            target = int(raw)
        elif raw.startswith("@"):
            target = raw
        elif raw:
            target = f"@{raw}"

    if not target:
        await message.answer(
            "❌ <b>Noto'g'ri format!</b>\n\n"
            "Iltimos, guruh havolasi, <b>@username</b> yoki <b>-100...</b> ID sini yuboring, "
            "yoki guruhdan bitta xabarni <b>Forward</b> qiling.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_groups")]
            ]),
            parse_mode="HTML"
        )
        return

    # 2. Get chat info from Telegram
    chat_info = None
    try:
        chat_info = await message.bot.get_chat(target)
    except Exception as e:
        # If target was already an integer, we might still accept it with fallback title
        if isinstance(target, int):
            chat_info = None
        else:
            await message.answer(
                f"❌ <b>Guruh topilmadi!</b>\n\n"
                f"Tafsilot: <code>{e}</code>\n\n"
                f"📌 <b>Tekshiring:</b>\n"
                f"1. Bot guruhga qo'shilgan va <b>Administrator</b> qilinganmi?\n"
                f"2. Guruh havolasi yoki @username to'g'rimi?\n\n"
                f"💡 <i>Eng oson usul: Guruhdan bitta xabarni bu yerga Forward qiling.</i>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_groups")]
                ]),
                parse_mode="HTML"
            )
            return

    group_id = int(chat_info.id) if chat_info else int(target)
    group_title = (chat_info.title if chat_info and chat_info.title else f"Guruh {group_id}")

    # 3. Check bot administrator status
    is_admin = False
    if chat_info:
        try:
            bot_member = await message.bot.get_chat_member(chat_id=group_id, user_id=message.bot.id)
            is_admin = bot_member.status in ('administrator', 'creator')
        except Exception:
            pass

    # 4. Save to Database
    from database.db import add_group
    await add_group(group_id, group_title)

    admin_status_note = ""
    if is_admin:
        admin_status_note = "\n🛡 <b>Bot holati:</b> Administrator ✅"
    else:
        admin_status_note = (
            "\n\n⚠️ <b>DIQQAT:</b> Bot hozircha bu guruhda <b>Administrator</b> emas!\n"
            "Buyurtmalar guruhga yetkazilishi va bot to'liq ishlashi uchun botni guruhda <b>Administrator</b> qiling."
        )

    await message.answer(
        f"✅ <b>Guruh muvaffaqiyatli ulandi!</b>\n\n"
        f"💬 Nomi: <b>{group_title}</b>\n"
        f"🆔 ID: <code>{group_id}</code>"
        f"{admin_status_note}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Guruhlar ro'yxatiga qaytish", callback_data="adm_groups")]
        ]),
        parse_mode="HTML"
    )
    await state.clear()


