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
    "👥 Guruh & Kanal":    "adm_groups",
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
        "adm_groups":    "👥 Guruh va Kanallar",
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

@router.callback_query(F.data.in_({"adm_groups", "adm_sub"}), admin_filter)
async def adm_groups_list(callback: types.CallbackQuery):
    await callback.answer()
    from database.db import get_all_groups, get_active_channels, get_setting
    
    groups = await get_all_groups()
    channels = await get_active_channels()
    sub_en = await get_setting('sub_enabled', '0')
    sub_icon = "✅ YOQILGAN" if sub_en == '1' else "❌ O'CHIRILGAN"
    gb_enabled = await get_setting('group_broadcasting_enabled', '1')
    gb_status = "✅ YOQILGAN" if gb_enabled == '1' else "❌ O'CHIRILGAN"
    
    text = (
        "👥 <b>GURUH VA KANALLAR BOSHQARUVI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📢 <b>Guruhlarga efir:</b> {gb_status}\n"
        f"🛡 <b>Majburiy obuna:</b> {sub_icon}\n"
        f"💬 <b>Buyurtma guruhlari:</b> {len(groups)} ta\n"
        f"📢 <b>Majburiy kanallar:</b> {len(channels)} ta\n\n"
        "<i>Quyidagi tugmalar orqali boshqaring:</i>"
    )
    
    rows = [
        [
            InlineKeyboardButton(text=f"📢 Efir: {gb_status}", callback_data="toggle_gb_global"),
            InlineKeyboardButton(text=f"🛡 Obuna: {sub_icon}", callback_data="toggle_sub_global")
        ]
    ]
    
    if groups:
        rows.append([InlineKeyboardButton(text="--- 💬 BUYURTMA GURUHLARI ---", callback_data="none")])
        for g in groups[:10]:
            rows.append([
                InlineKeyboardButton(text="🚕✅" if g[3] == 1 else "🚕❌", callback_data=f"toggle_group_taxi_{g[0]}"),
                InlineKeyboardButton(text="📦✅" if g[4] == 1 else "📦❌", callback_data=f"toggle_group_parcel_{g[0]}"),
                InlineKeyboardButton(text=f"🗑 {g[1] or g[0]}", callback_data=f"del_group_{g[0]}")
            ])
            
    if channels:
        rows.append([InlineKeyboardButton(text="--- 📢 MAJBURIY KANALLAR ---", callback_data="none")])
        for ch in channels[:5]:
            rows.append([
                InlineKeyboardButton(text=f"🗑 {ch[1] or ch[0]}", callback_data=f"del_channel_{ch[0]}")
            ])
            
    rows.append([
        InlineKeyboardButton(text="➕ Guruh qo'shish", callback_data="adm_add_group_manual"),
        InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="ch_add")
    ])
    rows.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")])
    
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    except:
        pass


@router.callback_query(F.data == "toggle_sub_global", admin_filter)
async def toggle_sub_global_handler(callback: types.CallbackQuery):
    from database.db import get_setting, update_setting
    curr = await get_setting('sub_enabled', '0')
    new_val = '0' if curr == '1' else '1'
    await update_setting('sub_enabled', new_val)
    await callback.answer("Majburiy obuna holati o'zgartirildi.")
    await adm_groups_list(callback)


@router.callback_query(F.data == "toggle_gb_global", admin_filter)
async def toggle_gb_global_handler(callback: types.CallbackQuery):
    from database.db import get_setting, update_setting
    curr = await get_setting('group_broadcasting_enabled', '1')
    new_val = '0' if curr == '1' else '1'
    await update_setting('group_broadcasting_enabled', new_val)
    status_text = "yoqildi" if new_val == '1' else "o'chirildi"
    await callback.answer(f"Global efir {status_text}")
    await adm_groups_list(callback)


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
    await adm_groups_list(callback)


@router.callback_query(F.data.startswith("del_group_"), admin_filter)
async def del_group_handler(callback: types.CallbackQuery):
    g_id = callback.data.replace("del_group_", "")
    from database.db import delete_group
    await delete_group(g_id)
    await callback.answer("Guruh o'chirildi.")
    await adm_groups_list(callback)


@router.callback_query(F.data.startswith("del_channel_"), admin_filter)
async def del_channel_handler(callback: types.CallbackQuery):
    ch_id = callback.data.replace("del_channel_", "")
    from database.db import remove_channel
    await remove_channel(ch_id)
    await callback.answer("Kanal o'chirildi.")
    await adm_groups_list(callback)


@router.callback_query(F.data == "adm_add_group_manual", admin_filter)
async def adm_add_group_manual_handler(callback: types.CallbackQuery, state: FSMContext):
    from utils.states import AdminStates
    await state.set_state(AdminStates.adding_group_id)
    await callback.answer()
    try:
        await callback.message.edit_text(
            "➕ <b>Guruh ID yoki havolasini kiriting:</b>\n\nMasalan: <code>-1001234567890</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_groups")]]),
            parse_mode="HTML"
        )
    except:
        pass


@router.message(AdminStates.adding_group_id, admin_filter)
async def process_add_group_id(message: types.Message, state: FSMContext):
    g_id = message.text.strip()
    from database.db import add_group
    await add_group(g_id, f"Guruh {g_id}")
    await message.answer(f"✅ Guruh qo'shildi: {g_id}")
    await state.clear()

