from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from database.db import get_setting, update_setting, get_active_channels, add_channel, remove_channel, clear_all_channels
from utils.states import AdminStates
from utils.locales import get_trans
from .base import admin_filter
import asyncio

router = Router()

EDITABLE_TEXTS = {
    'help': {
        'help_taxi': '🚕 Taksi yordam', 'help_parcel': '📦 Pochta yordam',
        'help_earn': '💰 Pul ishlash yordam', 'help_wallet': '💳 Hamyon yordam',
        'help_safety': '🛡 Xavfsizlik yordam', 'help_admin': '👨‍💻 Admin yordam',
    },
    'buttons': {
        'order_taxi': '🚕 Taksi tugmasi', 'order_parcel': '📦 Pochta tugmasi',
        'my_orders': '📋 Buyurtmalarim tugmasi', 'profile': '👤 Profil tugmasi',
        'leaderboard': '📊 Reyting tugmasi', 'settings': '⚙️ Sozlamalar tugmasi',
        'back': '🔙 Ortga tugmasi', 'accept': '✅ Qabul qilish tugmasi',
    },
    'system': {
        'welcome_passenger': '👋 Yo\'lovchi kutib olish', 
        'greeting_reply': '👋 Umumiy salomlashish',
        'group_info_text': 'ℹ️ Guruhdagi /info matni',
        'bot_added_to_group': '🚕 Guruhga qo\'shilgandagi matn',
        'user_joined_group_msg': '👋 Guruhga a\'zo bo\'lgandagi matn',
        'ai_welcome': '🤖 AI xush kelibsiz matni',
    }
}

SETTINGS_LABELS = {
    'commission_rate_taxi': '🚕 Taksi komissiyasi (%)',
    'commission_rate_parcel': '📦 Pochta komissiyasi (%)',
    'cashback_rate': '📉 Keshbek miqdori (%)',
    'min_driver_balance': '💳 Haydovchi minimal balansi',
    'min_price': '📉 Minimal buyurtma narxi',
    'max_price': '📈 Maksimal buyurtma narxi',
    'ref_bonus': '👥 Referal bonusi',
    'trial_new_driver_amount': '🔢 Sinov muddati miqdori',
    'leaderboard_prize_amount': '💰 Reyting mukofoti',
    'priority_delay': '🕒 Prioritet kechikishi (sekund)',
    'priority_price_daily': '💎 Kunlik prioritet narxi',
    'tariff_daily_price': '📅 Kunlik reja narxi',
    'tariff_monthly_price': '🗓 Oylik reja narxi',
    'tariff_pax_price': '👤 Yo\'lovchi limiti narxi (1 ta)',
    'tariff_parcel_price': '📦 Pochta limiti narxi (1 ta)',
    'admin_url': '👨‍💻 Admin havolasi (t.me/...)',
    'night_surge_multiplier': '🌙 Tungi tarif koeffitsiyenti (masalan: 1.2)',
    'price_raise_step': '💰 Narx oshirish qadami (so\'m)',
    'eskiz_email': '📧 Eskiz.uz Email',
    'eskiz_password': '🔑 Eskiz.uz Password',
    'eskiz_token': '🎫 Eskiz.uz Token (optional)',
}

@router.callback_query(F.data == "adm_settings", admin_filter)
async def settings_menu(callback: types.CallbackQuery):
    await callback.answer()
    maintenance = await get_setting('bot_maintenance', '0')
    is_comm = await get_setting('is_comm_enabled', '1')
    is_paid = await get_setting('is_paid_plan', '0')
    ai_en = await get_setting('ai_support_enabled', '0')
    
    m_icon = "🛑 ON" if maintenance == '1' else "🟢 OFF"
    comm_icon = "✅ ON" if is_comm == '1' else "❌ OFF"
    paid_icon = "✅ ON" if is_paid == '1' else "❌ OFF"
    ai_icon = "🤖 ON" if ai_en == '1' else "🤖 OFF"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔘 Menyu tugmalari nazorati", callback_data="adm_btn_mgmt")],
        
        [InlineKeyboardButton(text="📋 Tarif va Rejalar", callback_data="adm_tariff_prices"),
         InlineKeyboardButton(text="🎁 Bonus va Trial", callback_data="adm_trial_settings")],
        
        [InlineKeyboardButton(text="📝 Bot Kontenti & Matnlar", callback_data="adm_content"),
         InlineKeyboardButton(text="🤖 Avto-javob (FAQ)", callback_data="adm_autoreply")],
        
        [InlineKeyboardButton(text=f"💰 Komissiya: {comm_icon}", callback_data="toggle_is_comm_enabled"),
         InlineKeyboardButton(text=f"🤖 AI Yordamchi: {ai_icon}", callback_data="toggle_ai_support_enabled")],
        
        [InlineKeyboardButton(text=f"🛠 Texnik tanaffus: {m_icon}", callback_data="toggle_maintenance"),
         InlineKeyboardButton(text="📝 Admin Loglari", callback_data="adm_logs")],
        
        [InlineKeyboardButton(text="📱 SMS (Eskiz.uz)", callback_data="adm_sms_settings"),
         InlineKeyboardButton(text="👨‍💻 Admin havolasi", callback_data="cfg_admin_url")],
        
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")]
    ])
    await callback.message.edit_text("⚙️ <b>MARKAZIY SOZLAMALAR MARKAZI:</b>\n\nBarcha tizim parametrlari va bot sozlamalarini boshqarish uchun bo'limni tanlang:", reply_markup=kb, parse_mode="HTML")



@router.callback_query(F.data == "adm_content", admin_filter)
async def adm_content_menu(callback: types.CallbackQuery):
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Yordam matnlari", callback_data="edit_txt_cat_help")],
        [InlineKeyboardButton(text="🔘 Tugma matnlari", callback_data="edit_txt_cat_buttons")],
        [InlineKeyboardButton(text="💬 Salomlashish matnlari", callback_data="edit_txt_cat_system")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")]
    ])
    await callback.message.edit_text("📝 <b>BOT KONTENTINI BOSHQARISH</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("edit_txt_cat_"), admin_filter)
async def edit_txt_category(callback: types.CallbackQuery):
    await callback.answer()
    cat = callback.data.replace("edit_txt_cat_", "")
    texts = EDITABLE_TEXTS.get(cat, {})
    rows = [[InlineKeyboardButton(text=label, callback_data=f"edit_txt_key_{key}")] for key, label in texts.items()]
    rows.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_content")])
    await callback.message.edit_text(f"📝 <b>{cat.upper()}</b> bo'limi:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

@router.callback_query(F.data.startswith("edit_txt_key_"), admin_filter)
async def edit_txt_select_lang(callback: types.CallbackQuery):
    await callback.answer()
    key = callback.data.replace("edit_txt_key_", "")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data=f"edit_txt_lang_{key}_uz")],
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data=f"edit_txt_lang_{key}_ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data=f"edit_txt_lang_{key}_en")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_content")]
    ])
    await callback.message.edit_text(f"🌐 <b>{key}</b> uchun tilni tanlang:", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("edit_txt_lang_"), admin_filter)
async def edit_txt_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split("_"); lang = parts[-1]; key = "_".join(parts[3:-1])
    await state.update_data(edit_key=key, edit_lang=lang)
    await state.set_state(AdminStates.waiting_for_content_text)
    current_text = get_trans(lang, key)
    await callback.message.edit_text(f"📝 <b>Matnni tahrirlash</b>\nKalit: <code>{key}</code>\nTil: <b>{lang}</b>\n\nHozirgi matn:\n<pre>{current_text}</pre>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor", callback_data="adm_content")]]), parse_mode="HTML")

@router.message(AdminStates.waiting_for_content_text, admin_filter)
async def process_txt_edit(message: types.Message, state: FSMContext):
    data = await state.get_data(); key = data.get('edit_key'); lang = data.get('edit_lang')
    if not key or not lang: 
        import logging
        logging.getLogger(__name__).error(f"Missing key or lang in process_txt_edit: key={key}, lang={lang}")
        return await message.answer("❌ Xatolik.")
    
    import logging
    logging.getLogger(__name__).info(f"Updating setting txt_{key}_{lang} to: {message.text[:50]}...")
    await update_setting(f"txt_{key}_{lang}", message.text)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_content")]])
    await message.answer(f"✅ <b>Matn saqlandi!</b>", reply_markup=kb, parse_mode="HTML")
    await state.clear()

@router.callback_query(F.data == "adm_sub", admin_filter)
async def sub_menu(callback: types.CallbackQuery):
    await callback.answer()
    sub_en = await get_setting('sub_enabled', '0'); channels = await get_active_channels()
    text = f"🛡 <b>Majburiy obuna:</b> {'🟢 ON' if sub_en == '1' else '🔴 OFF'}\n\n"
    kb = []
    for cid, link in channels:
        text += f"✅ <b>{cid}</b> | <a href='{link}'>Link</a>\n"
        kb.append([InlineKeyboardButton(text=f"🗑 O'chirish: {cid}", callback_data=f"ch_del_{cid}")])
    if channels:
        kb.append([InlineKeyboardButton(text="🗑 Barchasini o'chirish", callback_data="ch_clear_all")])
    kb.extend([[InlineKeyboardButton(text="➕ Qo'shish", callback_data="ch_add")], [InlineKeyboardButton(text="🔄 Toggle", callback_data="ch_toggle")], [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")]])
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML", disable_web_page_preview=True)
    except:
        pass

@router.callback_query(F.data == "ch_toggle", admin_filter)
async def sub_toggle(callback: types.CallbackQuery):
    curr = await get_setting('sub_enabled', '0'); await update_setting('sub_enabled', '1' if curr == '0' else '0'); await sub_menu(callback)

@router.callback_query(F.data == "ch_add", admin_filter)
async def ch_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.adding_channel_id); await callback.message.edit_text("Kanal ID yoki @username:")

@router.message(AdminStates.adding_channel_id, admin_filter)
async def ch_add_id(message: types.Message, state: FSMContext):
    cid = message.text.strip()
    if "/" in cid and not cid.startswith("-100"):
        # If user pasted a link instead of ID/@username, try to extract username
        if "t.me/" in cid:
            parts = cid.split("t.me/")[-1].split("/")
            if parts:
                extracted = parts[0].split("?")[0]
                if extracted: cid = f"@{extracted}"
    
    # Simple validation: must be @username or start with -100
    if not (cid.startswith("@") or cid.startswith("-100")):
        await message.answer("❌ <b>Xato:</b> Kanal ID -100 bilan boshlanishi yoki @username bo'lishi kerak!")
        return

    await state.update_data(cid=cid)
    await state.set_state(AdminStates.adding_channel_link)
    await message.answer("<b>Taklif havolasi:</b>\n(Masalan: https://t.me/...)")

@router.message(AdminStates.adding_channel_link, admin_filter)
async def ch_add_finish(message: types.Message, state: FSMContext):
    link = message.text.strip()
    if not link.startswith("http"):
        await message.answer("❌ <b>Xato:</b> Havola http:// yoki https:// bilan boshlanishi kerak!")
        return
        
    data = await state.get_data()
    await add_channel(data['cid'], link)
    await message.answer(f"✅ <b>Kanal muvaffaqiyatli qo'shildi!</b>\n🆔 ID: <code>{data['cid']}</code>\n🔗 Link: {link}", parse_mode="HTML")
    await state.clear()

# --- ❤️ CHARITY MANAGEMENT ---
@router.callback_query(F.data == "adm_charity_mgmt", admin_filter)
async def adm_charity_mgmt_menu(callback: types.CallbackQuery):
    await callback.answer()
    card = await get_setting('charity_card', "O'rnatilmagan")
    p_total = await get_setting('charity_p_total', '0')
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Karta: {card}", callback_data="cfg_charity_card")],
        [InlineKeyboardButton(text=f"📅 Doimiy Total: {p_total}", callback_data="cfg_charity_p_total")],
        [InlineKeyboardButton(text="📝 Doimiy Matn", callback_data="cfg_charity_p_info")],
        [InlineKeyboardButton(text="➕ Yangi Maqsadli Ehson", callback_data="adm_charity_create")],
        [InlineKeyboardButton(text="📋 Faol Maqsadli Ehsonlar", callback_data="adm_charity_list")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_settings")]
    ])
    await callback.message.edit_text("❤️ <b>Ehson bo'limi boshqaruvi:</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "cfg_charity_p_info", admin_filter)
async def cfg_charity_p_info_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    current_text = await get_setting('charity_p_info', 'Oylik xayriya yig\'uvi.')
    await state.update_data(cfg_key='charity_p_info', cfg_label='Doimiy Ehson matni')
    await state.set_state(AdminStates.waiting_for_setting_value)
    await callback.message.edit_text(
        f"📝 <b>Doimiy Ehson matni</b>\n\nHozirgi matn:\n<pre>{current_text}</pre>\n\nYangi matnni kiriting:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor", callback_data="adm_charity_mgmt")]
        ]),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "adm_charity_list", admin_filter)
async def adm_charity_list_handler(callback: types.CallbackQuery):
    await callback.answer()
    from database.db import get_active_targeted_charities
    charities = await get_active_targeted_charities()
    
    if not charities:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_charity_mgmt")]
        ])
        return await callback.message.edit_text(
            "📋 <b>Faol maqsadli ehsonlar yo'q.</b>\n\nYangi maqsadli ehson yaratish uchun 'Yangi Maqsadli Ehson' tugmasini bosing.",
            reply_markup=kb, parse_mode="HTML"
        )
    
    text = "📋 <b>FAOL MAQSADLI EHSONLAR:</b>\n━━━━━━━━━━━━━━\n"
    kb_rows = []
    for c in charities:
        cid, title, desc, target, current, expiry = c[0], c[1], c[2], c[3], c[4], c[5]
        try: progress = int(float(current) / float(target) * 100)
        except: progress = 0
        text += f"\n✨ <b>{title}</b>\n"
        text += f"📊 {int(float(current)):,} / {int(float(target)):,} so'm ({progress}%)\n"
        text += f"📅 Muddat: <b>{expiry}</b>\n"
        kb_rows.append([
            InlineKeyboardButton(text=f"🗑 {title[:20]}ni o'chirish", callback_data=f"adm_charity_del_{cid}")
        ])
    
    kb_rows.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_charity_mgmt")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")

@router.callback_query(F.data.startswith("adm_charity_del_"), admin_filter)
async def adm_charity_del_handler(callback: types.CallbackQuery):
    cid = int(callback.data.replace("adm_charity_del_", ""))
    from database.db import delete_targeted_charity
    await delete_targeted_charity(cid)
    await callback.answer("✅ Ehson o'chirildi.")
    await adm_charity_list_handler(callback)

@router.callback_query(F.data.startswith("cfg_"), admin_filter)
async def cfg_start_handler(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.replace("cfg_", "")
    label = SETTINGS_LABELS.get(key, key)
    await state.update_data(cfg_key=key, cfg_label=label)
    await state.set_state(AdminStates.waiting_for_setting_value)
    await callback.answer()
    await callback.message.edit_text(f"📝 <b>{label}</b> uchun yangi qiymatni kiriting:", 
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor", callback_data="adm_settings")]]), parse_mode="HTML")

@router.message(AdminStates.waiting_for_setting_value, admin_filter)
async def cfg_process_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    key = data.get('cfg_key')
    label = data.get('cfg_label', key)
    if not key: return await state.clear()
    
    val = message.text.strip()
    await update_setting(key, val)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Ortga sozlamalarga", callback_data="adm_settings")]])
    await message.answer(f"✅ <b>{label}</b> yangilandi: <code>{val}</code>", reply_markup=kb, parse_mode="HTML")
    await state.clear()

@router.callback_query(F.data == "adm_btn_mgmt", admin_filter)
async def adm_btn_mgmt_menu(callback: types.CallbackQuery):
    await callback.answer()
    btns = [
        ('btn_order_taxi', '🚕 Taksi chaqirish'),
        ('btn_order_parcel', '📦 Pochta yuborish'),
        ('btn_rides', '💺 Hamroh reyslari'),
        ('btn_radar', '📡 Radar'),
        ('btn_app', '📱 Web App'),
        ('btn_my_orders', '📋 Buyurtmalarim'),
        ('btn_leaderboard', '📊 Reyting'),
        ('btn_bonus', '🎁 Bonus'),
        ('btn_promo', '🎫 Promokod'),
        ('btn_wallet', '💳 Hamyon'),
        ('btn_profile', '👤 Profil'),
        ('btn_referral', '👥 Referral'),
        ('btn_manual', '📖 Qo\'llanma'),
        ('btn_charity', '❤️ Ehson'),
        ('btn_priority', '💎 Prioritet'),
        ('btn_chat', '💬 Chat'),
        ('btn_live_location', '📍 Jonli lokatsiya'),
        ('btn_add_group', '➕ Guruh qo\'shish'),
        ('btn_write_admin', '👨‍💻 Adminga yozish'),
        ('btn_ai', '🤖 AI Savol-Javob'),
    ]

    rows = []
    # Bulk actions row
    rows.append([
        InlineKeyboardButton(text="✅ Hammasini yoq", callback_data="btn_bulk_all_on"),
        InlineKeyboardButton(text="❌ Hammasini o'chir", callback_data="btn_bulk_all_off"),
    ])

    current_row = []
    for key, label in btns:
        status = await get_setting(key, '1')
        icon = "✅" if status == '1' else "❌"
        current_row.append(InlineKeyboardButton(text=f"{icon} {label}", callback_data=f"toggle_btn_{key}"))
        
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
            
    if current_row:
        rows.append(current_row)

    rows.append([InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_settings")])

    try:
        await callback.message.edit_text(
            "🔘 <b>TUGMALAR NAZORATI VA BOSHQARUVI:</b>\n"
            "├ ✅ = Mijoz menyusida <b>ko'rinadi</b>\n"
            "└ ❌ = Mijoz menyusida <b>ko'rinmaydi</b>\n\n"
            "Tugmaga bosib holatni o'zgartiring:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML"
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error in adm_btn_mgmt_menu: {e}")

@router.callback_query(F.data == "noop", admin_filter)
async def noop_handler(callback: types.CallbackQuery):
    await callback.answer()

@router.callback_query(F.data == "btn_bulk_all_on", admin_filter)
async def btn_bulk_all_on(callback: types.CallbackQuery):
    from database.db import update_settings_bulk
    keys = [
        'btn_order_taxi','btn_order_parcel','btn_rides','btn_radar','btn_app','btn_my_orders',
        'btn_leaderboard','btn_bonus','btn_promo','btn_wallet',
        'btn_profile','btn_referral','btn_manual','btn_charity',
        'btn_priority','btn_chat','btn_live_location','btn_add_group',
        'btn_write_admin', 'btn_ai'
    ]
    settings_dict = {key: '1' for key in keys}
    await update_settings_bulk(settings_dict)
    await callback.answer("✅ Barcha tugmalar yoqildi!")
    await adm_btn_mgmt_menu(callback)

@router.callback_query(F.data == "btn_bulk_all_off", admin_filter)
async def btn_bulk_all_off(callback: types.CallbackQuery):
    from database.db import update_settings_bulk
    keys = [
        'btn_order_taxi','btn_order_parcel','btn_rides','btn_radar','btn_app','btn_my_orders',
        'btn_leaderboard','btn_bonus','btn_promo','btn_wallet',
        'btn_profile','btn_referral','btn_manual','btn_charity',
        'btn_priority','btn_chat','btn_live_location','btn_add_group',
        'btn_write_admin', 'btn_ai'
    ]
    settings_dict = {key: '0' for key in keys}
    await update_settings_bulk(settings_dict)
    await callback.answer("❌ Barcha tugmalar o'chirildi!")
    await adm_btn_mgmt_menu(callback)


@router.callback_query(F.data.startswith("toggle_btn_"), admin_filter)
async def toggle_btn_handler(callback: types.CallbackQuery):
    key = callback.data.replace("toggle_btn_", "")
    curr = await get_setting(key, '1')
    new_val = '0' if curr == '1' else '1'
    await update_setting(key, new_val)
    status_text = "✅ Yoqildi" if new_val == '1' else "❌ O'chirildi"
    await callback.answer(status_text)
    await adm_btn_mgmt_menu(callback)

@router.callback_query(F.data == "adm_tariff_prices", admin_filter)
async def adm_tariff_prices_menu(callback: types.CallbackQuery):
    await callback.answer()
    min_p = await get_setting('min_price', '5000')
    max_p = await get_setting('max_price', '100000')
    daily_p = await get_setting('tariff_daily_price', '5000')
    monthly_p = await get_setting('tariff_monthly_price', '100000')
    pax_limit_p = await get_setting('tariff_pax_price', '1000')
    parcel_limit_p = await get_setting('tariff_parcel_price', '1000')
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📉 Min buyurtma: {min_p} sum", callback_data="cfg_min_price")],
        [InlineKeyboardButton(text=f"📈 Max buyurtma: {max_p} sum", callback_data="cfg_max_price")],
        [InlineKeyboardButton(text=f"📅 Kunlik reja: {daily_p} sum", callback_data="cfg_tariff_daily_price")],
        [InlineKeyboardButton(text=f"🗓 Oylik reja: {monthly_p} sum", callback_data="cfg_tariff_monthly_price")],
        [InlineKeyboardButton(text=f"👤 Odam limiti (1 ta): {pax_limit_p} sum", callback_data="cfg_tariff_pax_price")],
        [InlineKeyboardButton(text=f"📦 Pochta limiti (1 ta): {parcel_limit_p} sum", callback_data="cfg_tariff_parcel_price")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_settings")]
    ])
    await callback.message.edit_text("📋 <b>Tariflar va Rejalar narxlari:</b>", reply_markup=kb, parse_mode="HTML")

# --- 🎁 BONUS & TRIAL ---
@router.callback_query(F.data == "adm_trial_settings", admin_filter)
async def adm_trial_settings_menu(callback: types.CallbackQuery):
    await callback.answer()
    ref = await get_setting('ref_bonus', '500')
    trial_en = await get_setting('trial_new_driver_enabled', '1')
    trial_amt = await get_setting('trial_new_driver_amount', '3')
    trial_type = await get_setting('trial_new_driver_type', 'days')
    
    icon = "✅" if trial_en == '1' else "❌"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"👥 Ref. bonus: {ref} sum", callback_data="cfg_ref_bonus")],
        [InlineKeyboardButton(text=f"{icon} Sinov muddati (Trial)", callback_data="toggle_trial")],
        [InlineKeyboardButton(text=f"🔢 Trial miqdori: {trial_amt} {trial_type}", callback_data="cfg_trial_new_driver_amount")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_settings")]
    ])
    await callback.message.edit_text("🎁 <b>Bonus va Sinov muddati:</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "toggle_trial", admin_filter)
async def toggle_trial_handler(callback: types.CallbackQuery):
    curr = await get_setting('trial_new_driver_enabled', '1')
    await update_setting('trial_new_driver_enabled', '0' if curr == '1' else '1')
    await adm_trial_settings_menu(callback)

# --- ⭐ RATING & LEADERBOARD ---
@router.callback_query(F.data == "adm_leaderboard_settings", admin_filter)
async def adm_leaderboard_menu(callback: types.CallbackQuery):
    await callback.answer()
    en = await get_setting('leaderboard_enabled', '1')
    prize = await get_setting('leaderboard_prize_amount', '10000')
    icon = "✅" if en == '1' else "❌"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{icon} Reyting tizimi", callback_data="toggle_lb")],
        [InlineKeyboardButton(text=f"💰 Mukofot: {prize} sum", callback_data="cfg_leaderboard_prize_amount")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_settings")]
    ])
    await callback.message.edit_text("⭐ <b>Reyting va Haftalik g'oliblar:</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "toggle_lb", admin_filter)
async def toggle_lb_handler(callback: types.CallbackQuery):
    curr = await get_setting('leaderboard_enabled', '1')
    await update_setting('leaderboard_enabled', '0' if curr == '1' else '1')
    await adm_leaderboard_menu(callback)

# --- ⚡ PRIORITY & QUEUE ---
@router.callback_query(F.data == "adm_priority_settings", admin_filter)
async def adm_priority_menu(callback: types.CallbackQuery):
    await callback.answer()
    delay = await get_setting('priority_delay', '10')
    price = await get_setting('priority_price_daily', '5000')
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🕒 Kechikish: {delay} sek", callback_data="cfg_priority_delay")],
        [InlineKeyboardButton(text=f"💎 Kunlik narx: {price} sum", callback_data="cfg_priority_price_daily")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_settings")]
    ])
    await callback.message.edit_text("⚡ <b>Prioritet (Navbat) sozlamalari:</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("ch_del_"), admin_filter)
async def ch_del_handler(callback: types.CallbackQuery):
    cid = callback.data.replace("ch_del_", "")
    await remove_channel(cid)
    await callback.answer("O'chirildi.")
    await sub_menu(callback)
    
@router.callback_query(F.data == "ch_clear_all", admin_filter)
async def ch_clear_all_handler(callback: types.CallbackQuery):
    await clear_all_channels()
    await callback.answer("✅ Barcha kanallar o'chirildi.", show_alert=True)
    await sub_menu(callback)

@router.callback_query(F.data == "toggle_maintenance", admin_filter)
async def toggle_maintenance_handler(callback: types.CallbackQuery):
    curr = await get_setting('bot_maintenance', '0')
    new_val = '1' if curr == '0' else '0'
    await update_setting('bot_maintenance', new_val)
    status_text = "🔴 Texnik tanaffus yoqildi" if new_val == '1' else "🟢 Bot ishchi holatga qaytdi"
    await callback.answer(status_text, show_alert=True)
    await settings_menu(callback)

@router.callback_query(F.data == "adm_sms_settings", admin_filter)
async def adm_sms_settings_menu(callback: types.CallbackQuery):
    await callback.answer()
    email = await get_setting('eskiz_email', 'Yo\'q')
    token = await get_setting('eskiz_token', 'Yo\'q')
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📧 Email: {email}", callback_data="cfg_eskiz_email")],
        [InlineKeyboardButton(text=f"🔑 Password", callback_data="cfg_eskiz_password")],
        [InlineKeyboardButton(text=f"🎫 Token: {token[:10]}...", callback_data="cfg_eskiz_token")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_settings")]
    ])
    await callback.message.edit_text("📱 <b>Eskiz.uz SMS Xizmati:</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "toggle_ai_support_enabled", admin_filter)
async def toggle_ai_support_handler(callback: types.CallbackQuery):
    curr = await get_setting('ai_support_enabled', '0')
    new_val = '1' if curr == '0' else '0'
    await update_setting('ai_support_enabled', new_val)
    status_text = "🤖 AI Yordamchi yoqildi" if new_val == '1' else "🤖 AI Yordamchi o'chirildi"
    await callback.answer(status_text)
    await settings_menu(callback)


# --- New Charity Creation Flow ---
@router.callback_query(F.data == "adm_charity_create", admin_filter)
async def adm_charity_create_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_charity_title)
    await callback.message.edit_text("📝 <b>Ehson sarlavhasini kiriting:</b>\n(Masalan: <i>Bemor bolakay uchun yordam</i>)")

@router.message(AdminStates.waiting_for_charity_title, admin_filter)
async def adm_charity_title(message: types.Message, state: FSMContext):
    await state.update_data(c_title=message.text)
    await state.set_state(AdminStates.waiting_for_charity_desc)
    await message.answer("📝 <b>Ehson haqida batafsil ma'lumot (matn) yuboring:</b>")

@router.message(AdminStates.waiting_for_charity_desc, admin_filter)
async def adm_charity_desc(message: types.Message, state: FSMContext):
    await state.update_data(c_desc=message.text)
    await state.set_state(AdminStates.waiting_for_charity_target)
    await message.answer("💰 <b>Maqsadli summani kiriting (faqat raqam):</b>")

@router.message(AdminStates.waiting_for_charity_target, admin_filter)
async def adm_charity_target(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam kiriting!")
    await state.update_data(c_target=int(message.text))
    await state.set_state(AdminStates.waiting_for_charity_expiry)
    await message.answer("📅 <b>Muddatni kiriting (Format: DD.MM.YYYY):</b>\n(Masalan: <code>31.12.2026</code>)")

@router.message(AdminStates.waiting_for_charity_expiry, admin_filter)
async def adm_charity_expiry(message: types.Message, state: FSMContext):
    await state.update_data(c_expiry=message.text)
    await state.set_state(AdminStates.waiting_for_charity_media)
    await message.answer("📸 <b>Ehson uchun rasm yoki video yuboring:</b>")

@router.message(AdminStates.waiting_for_charity_media, admin_filter, F.photo | F.video)
async def adm_charity_media_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    m_type = 'photo' if message.photo else 'video'
    
    from database.db import add_targeted_charity, get_users_list, get_groups_list
    cid = await add_targeted_charity(data['c_title'], data['c_desc'], data['c_target'], data['c_expiry'], file_id, m_type)
    
    await message.answer(f"✅ <b>Maqsadli ehson yaratildi!</b>\n\nHozir barcha foydalanuvchi va guruhlarga yuboriladi...")
    await state.clear()
    
    # Broadcast to all users and groups
    users = await get_users_list()
    groups = await get_groups_list()
    all_targets = users + groups
    
    broadcast_text = (
        f"<b>🚨 YANGI EHSON YIG'UVI!</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"✨ <b>{data['c_title']}</b>\n\n"
        f"📝 {data['c_desc']}\n\n"
        f"💰 Maqsad: <b>{data['c_target']:,} so'm</b>\n"
        f"📅 Muddat: <b>{data['c_expiry']}</b> gacha\n\n"
        f"👇 Yordam berish uchun botga o'ting:\n"
        f"👉 @{(await message.bot.get_me()).username}"
    )
    
    success = 0
    for target_id in all_targets:
        try:
            if m_type == 'video':
                await message.bot.send_video(target_id, file_id, caption=broadcast_text, parse_mode="HTML")
            else:
                await message.bot.send_photo(target_id, file_id, caption=broadcast_text, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    
    await message.answer(f"📢 Xabar {success} ta chatga (user + guruh) yetkazildi.")

@router.callback_query(F.data.startswith("toggle_is_"), admin_filter)
async def toggle_setting_handler(callback: types.CallbackQuery):
    key = callback.data.replace("toggle_", "")
    curr = await get_setting(key, '1' if 'comm' in key else '0')
    new_val = '1' if curr == '0' else '0'
    await update_setting(key, new_val)
    await callback.answer("✅ Yangilandi")
    await settings_menu(callback)
