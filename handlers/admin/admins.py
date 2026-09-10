from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN_ID
from .base import admin_filter
from database.db import get_all_admins, add_admin, remove_admin, get_user
from aiogram.fsm.state import StatesGroup, State

router = Router()

PERM_NAMES = {
    "stats": "Statistika",
    "users": "Foydalanuvchilar",
    "drivers": "Haydovchilar",
    "orders": "Buyurtmalar",
    "broadcast": "Xabar yuborish",
    "groups": "Guruhlar",
    "sub": "Obunalar",
    "settings": "Sozlamalar",
    "btn_mgmt": "Tugmalar nazorati",
    "charity": "Ehson",
    "promo": "Promokodlar",
    "withdrawals": "Pul yechish",
    "logs": "Loglar",
    "content": "Kontent",
    "autoreply": "Avto-javob",
    "reports": "Hisobotlar",
    "promo_mtl": "Promo materiallar"
}

class AdminMgmtStates(StatesGroup):
    waiting_for_admin_id = State()
    choosing_permissions = State()

async def get_admin_mgmt_menu_content():
    admins = await get_all_admins()
    
    text = "<b>👑 Adminlar boshqaruvi</b>\n━━━━━━━━━━━━━━\n"
    kb = []
    
    for adm in admins:
        # user_id, role, permissions, added_at
        uid, role, perms, added_at = adm
        role_tag = "🔴 Glavniy" if role == 'main' else "🔵 Yordamchi"
        text += f"• <code>{uid}</code> [{role_tag}]\n"
        
        if role != 'main':
            if perms == 'all':
                text += f"   └ 🔑 <i>Barcha ruxsatlar</i>\n"
            elif perms == 'none':
                text += f"   └ 🔑 <i>Ruxsat yo'q</i>\n"
            else:
                translated_perms = ", ".join([PERM_NAMES.get(p, p) for p in perms.split(",")])
                text += f"   └ 🔑 <i>{translated_perms}</i>\n"
             
        if role != 'main':
            kb.append([
                InlineKeyboardButton(text=f"⚙️ Ruxsatlar", callback_data=f"adm_perms_{uid}"),
                InlineKeyboardButton(text=f"❌ O'chirish", callback_data=f"adm_remove_{uid}")
            ])
            
    kb.append([InlineKeyboardButton(text="➕ Yangi admin qo'shish", callback_data="adm_add_start")])
    kb.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")])
    
    return text, InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data == "adm_mgmt", admin_filter)
async def admin_mgmt_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("❌ Bu bo'limga faqat Glavniy admin kirishi mumkin!", show_alert=True)
    
    await callback.answer()
    text, markup = await get_admin_mgmt_menu_content()
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")

# Helper to get permission keyboard
def get_perms_kb(uid, current_perms):
    all_keys = ["stats", "users", "drivers", "orders", "broadcast", "groups", "sub", "settings", "btn_mgmt", "charity", "promo", "withdrawals", "logs", "content", "autoreply", "reports", "promo_mtl"]
    kb = []
    row = []
    
    perms = current_perms.split(",") if current_perms != 'all' else all_keys
    
    for k in all_keys:
        icon = "✅" if k in perms else "❌"
        name = PERM_NAMES.get(k, k)
        row.append(InlineKeyboardButton(text=f"{icon} {name}", callback_data=f"toggle_p_{uid}_{k}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row: kb.append(row)
    
    kb.append([InlineKeyboardButton(text="💾 Saqlash", callback_data=f"adm_perms_save_{uid}")])
    kb.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="adm_mgmt")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data.startswith("adm_perms_"), admin_filter)
async def adm_perms_edit(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    
    parts = callback.data.split("_")
    if parts[2] == 'save':
        await callback.answer("✅ Ruxsatlar saqlandi")
        return await admin_mgmt_menu(callback, state)
        
    uid = int(parts[2])
    from database.db import get_admin
    adm = await get_admin(uid)
    perms = adm[2] if adm else 'all'
    
    await callback.message.edit_text(f"🔑 <b>Admin ruxsatlarini sozlash:</b> <code>{uid}</code>", 
                                   reply_markup=get_perms_kb(uid, perms), parse_mode="HTML")

@router.callback_query(F.data.startswith("toggle_p_"), admin_filter)
async def adm_perms_toggle(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    
    # toggle_p_UID_KEY  (KEY may contain underscores like btn_mgmt, promo_mtl)
    parts = callback.data.split("_")
    uid = int(parts[2])
    key = "_".join(parts[3:])  # Join remaining parts to support multi-word keys
    
    from database.db import get_admin, update_setting # Actually we need a specific func or update_admin
    adm = await get_admin(uid)
    perms = adm[2] if adm else 'all'
    
    all_keys = ["stats", "users", "drivers", "orders", "broadcast", "groups", "sub", "settings", "btn_mgmt", "charity", "promo", "withdrawals", "logs", "content", "autoreply", "reports", "promo_mtl"]
    if perms == 'all':
        perm_list = all_keys.copy()
    else:
        perm_list = perms.split(",")
        
    if key in perm_list:
        perm_list.remove(key)
    else:
        perm_list.append(key)
        
    new_perms = ",".join(perm_list) if len(perm_list) < len(all_keys) else 'all'
    if not perm_list: new_perms = "none"
    
    from database.db import add_admin # add_admin works as UPDATE due to INSERT OR REPLACE
    await add_admin(uid, 'assistant', new_perms)
    
    await callback.message.edit_reply_markup(reply_markup=get_perms_kb(uid, new_perms))

@router.callback_query(F.data == "adm_add_start", admin_filter)
async def adm_add_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await callback.answer()
    await state.set_state(AdminMgmtStates.waiting_for_admin_id)
    await callback.message.edit_text(
        "➕ <b>Yangi yordamchi admin qo'shish</b>\n\nFoydalanuvchining ID raqamini kiriting:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_mgmt")]])
    )

@router.message(AdminMgmtStates.waiting_for_admin_id, admin_filter)
async def process_adm_add(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    if not message.text.isdigit():
        return await message.answer("❌ Iltimos, faqat ID (raqam) kiriting!")
    
    new_uid = int(message.text)
    user = await get_user(new_uid)
    
    if not user:
        return await message.answer("❌ Bu ID dagi foydalanuvchi bot bazasida topilmadi. Avval u botni boshlashi kerak.")
    
    await add_admin(new_uid, 'assistant', 'none') # Start with no permissions
    await message.answer(f"✅ Foydalanuvchi <code>{new_uid}</code> yordamchi admin qilib qo'shildi! Endi '⚙️ Ruxsatlar' tugmasi orqali huquqlarni belgilang.", parse_mode="HTML")
    await state.clear()
    
    # Show the menu again
    text, markup = await get_admin_mgmt_menu_content()
    await message.answer(text, reply_markup=markup, parse_mode="HTML")

@router.callback_query(F.data.startswith("adm_remove_"), admin_filter)
async def process_adm_remove(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    
    uid = int(callback.data.replace("adm_remove_", ""))
    await remove_admin(uid)
    await callback.answer("✅ Admin olib tashlandi")
    await admin_mgmt_menu(callback, state)
