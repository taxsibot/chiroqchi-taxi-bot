from aiogram import types, Router
from config import ADMIN_ID
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import BaseFilter


class AdminFilter(BaseFilter):
    async def __call__(self, event: types.Message | types.CallbackQuery) -> bool:
        from database.db import is_admin_db
        return event.from_user.id == ADMIN_ID or await is_admin_db(event.from_user.id)


admin_filter = AdminFilter()


# ─── PASTDAGI DOIMIY REPLY KEYBOARD (Admin Panel) ─────────────────────────────

def get_admin_reply_kb(user_id, permissions='all') -> ReplyKeyboardMarkup:
    """
    Returns a persistent bottom reply keyboard for the admin panel.
    Always visible at the bottom — never as a floating message bubble.
    """
    all_modules = [
        ("📊 Statistika",      "📊 Statistika"),
        ("👥 Foydalanuvchilar","👥 Foydalanuvchilar"),
        ("🚗 Haydovchilar",    "🚗 Haydovchilar"),
        ("📦 Buyurtmalar",     "📦 Buyurtmalar"),
        ("📢 Reklama",         "📢 Reklama"),
        ("👥 Guruh & Kanal",   "👥 Guruh & Kanal"),
        ("💳 Moliya",          "💳 Moliya"),
        ("⚙️ Sozlamalar",      "⚙️ Sozlamalar"),
    ]

    perm_list = permissions.split(",") if permissions != 'all' else None

    buttons = []
    row = []
    for label, _ in all_modules:
        key = label  # module key derived from label
        allowed = (
            permissions == 'all' or
            (perm_list and any(p in label.lower() for p in perm_list))
        )
        if allowed:
            row.append(KeyboardButton(text=label))
            if len(row) == 2:
                buttons.append(row)
                row = []
    if row:
        buttons.append(row)

    # Owner-only: manage sub-admins
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="👑 Adminlar")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        persistent=True,          # <-- doim pastda turadi (Telegram 7.0+)
        input_field_placeholder="🛠 Admin bo'limini tanlang..."
    )


# ─── INLINE KEYBOARD — faqat callback uchun (chuqur sahifalar uchun) ──────────

def get_admin_main_kb(user_id, permissions='all') -> InlineKeyboardMarkup:
    """
    Inline keyboard for deep-module pages (callback navigation).
    Used inside sub-sections, NOT as the main panel.
    """
    all_modules = [
        ("📊 Statistika & Hisobot", "adm_stats"),
        ("👥 Foydalanuvchilar",      "adm_users"),
        ("🚗 Haydovchilar",          "adm_drivers"),
        ("📦 Buyurtmalar",           "adm_orders"),
        ("📢 Reklama & Xabarnoma",   "adm_broadcast"),
        ("👥 Guruh va Kanallar",     "adm_groups"),
        ("💳 Moliya & Promokodlar",  "adm_finance"),
        ("⚙️ Tizim Sozlamalari",     "adm_settings"),
    ]

    is_main = user_id == ADMIN_ID
    kb = []
    current_row = []

    perm_list = permissions.split(",") if permissions != 'all' else None

    for label, data in all_modules:
        module_key = data.replace("adm_", "")
        if permissions == 'all' or (perm_list and module_key in perm_list):
            current_row.append(InlineKeyboardButton(text=label, callback_data=data))
            if len(current_row) == 2:
                kb.append(current_row)
                current_row = []

    if current_row:
        kb.append(current_row)

    if is_main:
        kb.append([InlineKeyboardButton(text="👑 Adminlar boshqaruvi", callback_data="adm_mgmt")])

    return InlineKeyboardMarkup(inline_keyboard=kb)
