from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types.web_app_info import WebAppInfo
from utils.locales import LANGUAGES, get_trans
from database.db import get_setting

def get_language_keyboard():
    # 2 columns per row
    langs = list(LANGUAGES.items())
    buttons = []
    for i in range(0, len(langs), 2):
        row = [InlineKeyboardButton(text=langs[i][1], callback_data=f"lang_{langs[i][0]}")]
        if i+1 < len(langs):
            row.append(InlineKeyboardButton(text=langs[i+1][1], callback_data=f"lang_{langs[i+1][0]}"))
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_role_keyboard(is_admin: bool = False, lang='uz'):
    buttons = [
        [KeyboardButton(text=get_trans(lang, 'role_passenger'))],
        [KeyboardButton(text=get_trans(lang, 'role_driver'))]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="🛠 Admin Panel")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_phone_keyboard(lang='uz'):
    # Primary phone is MANDATORY - no skip button
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 " + get_trans(lang, 'confirm_phone_btn'), request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_secondary_phone_keyboard(lang='uz'):
    # Secondary phone is OPTIONAL - keep skip button
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 " + get_trans(lang, 'confirm_phone_btn'), request_contact=True)],
            [KeyboardButton(text=get_trans(lang, 'skip'))]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

async def get_passenger_menu(is_admin: bool = False, has_active_order: bool = False, lang='uz'):
    from database.db import get_setting_sync
    bot_maintenance = get_setting_sync('bot_maintenance', '0')
    if bot_maintenance == '1' and not is_admin:
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⏳ Texnik tanaffus")]], resize_keyboard=True)

    btn_order_taxi = get_setting_sync('btn_order_taxi', '1')
    btn_order_parcel = get_setting_sync('btn_order_parcel', '1')
    btn_rides = get_setting_sync('btn_rides', '1')
    btn_my_orders = get_setting_sync('btn_my_orders', '1')
    btn_wallet = get_setting_sync('btn_wallet', '1')
    btn_profile = get_setting_sync('btn_profile', '1')
    btn_manual = get_setting_sync('btn_manual', '1')

    keyboard_list = []
    
    # Row 1: Main Taxi Button
    if btn_order_taxi == '1':
        keyboard_list.append([KeyboardButton(text="🚕 " + get_trans(lang, 'order_taxi').replace("🚕 ", ""))])

    # Row 2: Parcel & Hamroh rides
    row2 = []
    if btn_order_parcel == '1':
        row2.append(KeyboardButton(text="📦 " + get_trans(lang, 'order_parcel').replace("📦 ", "")))
    if btn_rides == '1':
        row2.append(KeyboardButton(text=get_trans(lang, 'rides_btn')))
    if row2:
        keyboard_list.append(row2)

    # Active order quick access
    if has_active_order:
        keyboard_list.append([KeyboardButton(text="⚡️ " + get_trans(lang, 'active_order_manage'))])

    # Row 3: My Orders & Wallet
    row3 = []
    if btn_my_orders == '1':
        row3.append(KeyboardButton(text="📋 " + get_trans(lang, 'my_orders').replace("📋 ", "")))
    if btn_wallet == '1':
        row3.append(KeyboardButton(text="💳 " + get_trans(lang, 'wallet').replace("💳 ", "")))
    if row3:
        keyboard_list.append(row3)

    # Row 4: Profile & Help
    row4 = []
    if btn_profile == '1':
        row4.append(KeyboardButton(text="👤 " + get_trans(lang, 'profile').replace("👤 ", "")))
    if btn_manual == '1':
        row4.append(KeyboardButton(text="📖 " + get_trans(lang, 'manual').replace("📖 ", "")))
    if row4:
        keyboard_list.append(row4)

    if is_admin:
        keyboard_list.append([KeyboardButton(text="🛠 Admin Panel")])
        
    return ReplyKeyboardMarkup(
        keyboard=keyboard_list,
        resize_keyboard=True
    )

async def get_driver_menu(is_online: bool, is_admin: bool = False, lang='uz'):
    from database.db import get_setting_sync
    bot_maintenance = get_setting_sync('bot_maintenance', '0')
    if bot_maintenance == '1' and not is_admin:
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⏳ Texnik tanaffus")]], resize_keyboard=True)

    btn_available_parcels = get_setting_sync('btn_available_parcels', '1')
    btn_route_config = get_setting_sync('btn_route_config', '1')
    btn_wallet = get_setting_sync('btn_wallet', '1')
    btn_my_orders = get_setting_sync('btn_my_orders', '1')
    btn_profile = get_setting_sync('btn_profile', '1')
    btn_driver_stats = get_setting_sync('btn_driver_stats', '1')

    status_text = "🔴 " + get_trans(lang, 'status_offline').replace("🔴 ", "") if is_online else "🟢 " + get_trans(lang, 'status_online').replace("🟢 ", "")
    
    keyboard_list = [
        [KeyboardButton(text=status_text)],
        [KeyboardButton(text=get_trans(lang, 'create_ride_btn')), KeyboardButton(text=get_trans(lang, 'return_trip_btn'))]
    ]

    # Row 2: Available parcels & Route settings
    row2 = []
    if btn_available_parcels == '1':
        row2.append(KeyboardButton(text="📦 " + get_trans(lang, 'available_parcels').replace("📦 ", "")))
    if btn_route_config == '1':
        row2.append(KeyboardButton(text="🛣 " + get_trans(lang, 'route_settings').replace("🛣 ", "")))
    if row2:
        keyboard_list.append(row2)

    # Row 3: Wallet & Orders
    row3 = []
    if btn_wallet == '1':
        row3.append(KeyboardButton(text="💳 " + get_trans(lang, 'wallet').replace("💳 ", "")))
    if btn_my_orders == '1':
        row3.append(KeyboardButton(text="📋 " + get_trans(lang, 'my_orders').replace("📋 ", "")))
    if row3:
        keyboard_list.append(row3)

    # Row 4: Profile & Stats
    row4 = []
    if btn_profile == '1':
        row4.append(KeyboardButton(text="👤 " + get_trans(lang, 'profile').replace("👤 ", "")))
    if btn_driver_stats == '1':
        row4.append(KeyboardButton(text="📈 " + get_trans(lang, 'driver_stats').replace("📈 ", "")))
    if row4:
        keyboard_list.append(row4)

    if is_admin:
        keyboard_list.append([KeyboardButton(text="🛠 Admin Panel")])
        
    return ReplyKeyboardMarkup(
        keyboard=keyboard_list,
        resize_keyboard=True
    )

        
    return ReplyKeyboardMarkup(
        keyboard=keyboard_list,
        resize_keyboard=True
    )


def get_passenger_count_keyboard(lang='uz'):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1"), KeyboardButton(text="2")],
            [KeyboardButton(text="3"), KeyboardButton(text="4")],
            [KeyboardButton(text="❌ " + get_trans(lang, 'cancel_order').replace("❌ ", ""))]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
