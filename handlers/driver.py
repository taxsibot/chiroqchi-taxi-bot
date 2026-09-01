from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
import asyncio
import logging
import math
from database.db import (
    get_driver, set_driver_status, accept_order, update_order_status, 
    get_online_driver_ids, get_order, get_driver_active_orders,
    get_user, get_user_language, get_setting, add_bid,
    set_driver_route, get_online_drivers_with_route, get_order_channels,
    get_weekly_leaderboard, get_driver_rank, update_order_live_location_msg,
    get_online_drivers_priority_data
)
from utils.route_helper import get_region, get_order_route
from keyboards.reply import get_driver_menu
from utils.utils import IsMenuButton, check_subscription
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.states import DriverStates
from utils.locales import get_trans
from config import ADMIN_ID
from datetime import datetime

router = Router()
logger = logging.getLogger(__name__)

BOT_INFO_CACHE = None

@router.message(F.chat.type == "private", IsMenuButton('status_online'))
@router.message(F.chat.type == "private", IsMenuButton('status_offline'))
async def toggle_driver_status(message: types.Message):
    is_online = any(x in message.text for x in ["🟢", "Bash", "Стать"]) or "Online" in message.text
    # Check current status from text or better yet, from DB or just toggle
    # If text has "Onlayn/Online/Стать онлайн" -> they want to be online
    target_online = "🟢" in message.text
    
    lang = await get_user_language(message.from_user.id)
    await set_driver_status(message.from_user.id, target_online)
    
    status_key = 'status_online' if target_online else 'status_offline'
    is_admin = message.from_user.id == ADMIN_ID
    await message.answer(
        f"<b>{get_trans(lang, status_key)}</b>", 
        reply_markup=await get_driver_menu(target_online, is_admin=is_admin, lang=lang), 
        parse_mode="HTML"
    )

async def broadcast_order(bot: Bot, order_id, from_loc, to_loc, price, passenger_count=1, scheduled_time=None, from_lat=None, from_lon=None, car_class='Standard', parcel_photo=None, order_type='taxi', is_update=False):
    """Sends new order to drivers using a 2-wave priority system with Smart Auto-Dispatch."""
    global BOT_INFO_CACHE
    bot_username = "chiroqchitaksibot"
    if BOT_INFO_CACHE and getattr(BOT_INFO_CACHE, 'username', None):
        bot_username = BOT_INFO_CACHE.username
    else:
        try:
            BOT_INFO_CACHE = await bot.get_me()
            bot_username = BOT_INFO_CACHE.username or "chiroqchitaksibot"
        except Exception as e:
            logger.warning(f"Could not get bot info in broadcast: {e}")

    # Get configuration from settings
    delay = int(await get_setting('priority_delay', '10'))
    gb_enabled = await get_setting('group_broadcasting_enabled', '1')

    # Fetch drivers data once at the start
    drivers_list = await get_online_drivers_priority_data()
    order_route = get_order_route(from_loc, to_loc)

    safe_from = from_loc
    safe_to = to_loc

    # ── Build message text ──────────────────────────────────────────
    class_label = "🚙 Standart" if car_class == 'Standard' else ("✨ Komfort" if car_class == 'Comfort' else "📦 Pochta")
    order_emoji = "📦" if order_type == 'parcel' else "🚕"

    if is_update:
        header = f"{order_emoji} <b>⬆️ NARX YANGILANDI!</b>"
    else:
        header = f"{order_emoji} <b>{'YANGI POCHTA BUYURTMASI!' if order_type == 'parcel' else 'YANGI BUYURTMA!'}</b>"

    now_time = datetime.now().strftime("%H:%M")

    common_text = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔢 <b>Buyurtma:</b> <code>#{order_id}</code>\n"
        f"📍 <b>Qayerdan:</b> <b>{safe_from}</b>\n"
        f"🏁 <b>Qayerga:</b> <b>{safe_to}</b>\n"
        f"💰 <b>Narxi:</b> <b>{int(price):,} so'm</b>\n"
    )
    if order_type == 'taxi':
        common_text += f"👥 <b>Yo'lovchilar:</b> {passenger_count} ta\n"
    if scheduled_time and scheduled_time not in ('Hozir', 'now', None):
        common_text += f"📅 <b>Vaqt:</b> {scheduled_time}\n"
    else:
        common_text += f"⏱ <b>Vaqt:</b> Hozir ({now_time})\n"
    common_text += (
        f"🚗 <b>Sinf:</b> {class_label}\n"
        f"━━━━━━━━━━━━━━\n"
        f"👇 <i>Quyidagi tugmani bosib buyurtmani oling!</i>"
    )

    # Keyboard for GROUP (direct accept + taxi order link)
    group_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"accept_{order_id}"),
            InlineKeyboardButton(text="🚕 Taksi chaqirish", url=f"https://t.me/{bot_username}?start=new"),
        ],
        [InlineKeyboardButton(text="🤖 Botga o'tish", url=f"https://t.me/{bot_username}?start=order_{order_id}")]
    ])

    # Keyboard for ADMIN notification
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Botga o'tish", url=f"https://t.me/{bot_username}?start=order_{order_id}")]
    ])

    # ── Phase 1: Group & Channel Broadcasting (IMMEDIATE) ──────────
    if gb_enabled == '1':
        group_ids = await get_order_channels(order_type=order_type)
        if not group_ids:
            from database.db import get_all_groups
            all_groups = await get_all_groups()
            group_ids = [g[0] for g in all_groups]

        if group_ids:
            for g_id in group_ids:
                try:
                    if parcel_photo:
                        try:
                            await bot.send_photo(g_id, parcel_photo, caption=common_text, reply_markup=group_kb, parse_mode="HTML")
                        except Exception:
                            await bot.send_message(g_id, common_text, reply_markup=group_kb, parse_mode="HTML")
                    else:
                        await bot.send_message(g_id, common_text, reply_markup=group_kb, parse_mode="HTML")
                    logger.info(f"Order #{order_id} broadcast to group/channel {g_id}")
                except Exception as e:
                    try:
                        fallback_text = f"{common_text}\n\n👉 <b>Buyurtmani olish:</b> https://t.me/{bot_username}?start=order_{order_id}"
                        await bot.send_message(g_id, fallback_text, parse_mode="HTML")
                        logger.info(f"Order #{order_id} broadcast fallback to {g_id}")
                    except Exception as e2:
                        logger.error(f"Broadcasting failed for group {g_id}: {e2}")



    # ── Phase 2: Admin Notification (IMMEDIATE) ─────────────────────
    if ADMIN_ID and ADMIN_ID != 0:
        admin_text = f"🛡 <b>ADMIN MONITORING</b>\n{common_text}"
        try:
            if parcel_photo:
                await bot.send_photo(ADMIN_ID, parcel_photo, caption=admin_text, reply_markup=admin_kb, parse_mode="HTML")
            else:
                await bot.send_message(ADMIN_ID, admin_text, reply_markup=admin_kb, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to send admin monitoring message: {e}")

    # --- Smart Auto-Dispatch Logic ---
    auto_dispatch_enabled = await get_setting('auto_dispatch_enabled', '1') == '1'
    auto_dispatch_radius = float(await get_setting('auto_dispatch_radius', '5'))

    def get_distance(d_lat, d_lon):
        if None in (from_lat, from_lon, d_lat, d_lon):
            return None
        try:
            # Haversine formula
            R = 6371.0 # Earth radius in km
            dlat = math.radians(d_lat - from_lat)
            dlon = math.radians(d_lon - from_lon)
            a = math.sin(dlat / 2)**2 + math.cos(math.radians(from_lat)) * math.cos(math.radians(d_lat)) * math.sin(dlon / 2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            return R * c
        except Exception:
            return None

    # Calculate distance for each online driver
    drivers_with_distance = []
    for d in drivers_list:
        # d: user_id(0), has_priority(1), work_type(2), active_route(3), lat(4), lon(5)
        d_lat, d_lon = d[4], d[5]
        dist = get_distance(d_lat, d_lon)
        drivers_with_distance.append((d[0], d[1], d[2], d[3], dist))

    # Apply Auto-Dispatch filter if active and coordinates exist
    is_smart_dispatched = False
    filtered_drivers = drivers_with_distance
    
    if auto_dispatch_enabled and from_lat is not None and from_lon is not None:
        radius_drivers = [d for d in drivers_with_distance if d[4] is not None and d[4] <= auto_dispatch_radius]
        if radius_drivers:
            filtered_drivers = radius_drivers
            is_smart_dispatched = True
            logger.info(f"Smart Auto-Dispatch: Found {len(radius_drivers)} drivers within {auto_dispatch_radius}km for order #{order_id}")
        else:
            logger.info(f"Smart Auto-Dispatch: No drivers within {auto_dispatch_radius}km for order #{order_id}. Falling back to all online drivers.")

    async def send_to_driver(driver_id, distance=None):
        lang = await get_user_language(driver_id)
        class_key = 'class_comfort' if car_class == 'Comfort' else 'class_standard'
        class_text = get_trans(lang, class_key)
        
        buttons = [
            [InlineKeyboardButton(text=get_trans(lang, 'accept'), callback_data=f"accept_{order_id}")],
            [InlineKeyboardButton(text=f"💰 {get_trans(lang, 'order_taxi') if order_type == 'taxi' else get_trans(lang, 'order_parcel')}", callback_data=f"bid_{order_id}")],
            [InlineKeyboardButton(text="❌", callback_data="decline_order")]
        ]
        if from_lat and from_lon:
            buttons.insert(0, [InlineKeyboardButton(text="📍 Map", url=f"https://www.google.com/maps?q={from_lat},{from_lon}")])
        
        time_text = f"\n📅 <b>{scheduled_time}</b>" if scheduled_time and scheduled_time != 'Hozir' else ""
        
        if order_type == 'parcel':
            text = get_trans(lang, 'parcel_broadcast').format(
                from_loc=safe_from, to_loc=safe_to, price=price, time_text=time_text
            )
        else:
            text = get_trans(lang, 'order_broadcast').format(
                from_loc=safe_from, to_loc=safe_to, count=passenger_count, price=price, time_text=time_text
            )
        text += f"\n🚗 <b>{get_trans(lang, 'profile_class').split(':')[0]}:</b> {class_text}"
        
        # Display distance to driver if available
        if distance is not None:
            dist_label = f"📍 <b>Masofa sizgacha: ~{distance:.1f} km</b>" if lang == 'uz' else f"📍 <b>Расстояние до вас: ~{distance:.1f} км</b>"
            text += f"\n{dist_label}"
        
        try:
            if parcel_photo:
                await bot.send_photo(driver_id, parcel_photo, caption=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
            else:
                await bot.send_message(driver_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to send order to {driver_id}: {e}")

    # WAVE 1: Priority Drivers (IMMEDIATE)
    priority_drivers = [d for d in filtered_drivers if d[1] == 1 and (d[2] == 'both' or d[2] == order_type) and (d[3] == 'all' or d[3] == order_route)]
    if priority_drivers:
        await asyncio.gather(*[send_to_driver(d[0], d[4]) for d in priority_drivers], return_exceptions=True)
        
    # WAVE 2: Normal Drivers (after delay)
    if any(d[1] == 0 for d in filtered_drivers): # Only sleep if there are normal drivers
        await asyncio.sleep(delay)
        
        # CRITICAL FIX: Check if order is still pending before sending to wave 2
        order = await get_order(order_id)
        if not order or order[11] != 'pending':
            logger.info(f"Broadcast for order #{order_id} stopped: order already taken or cancelled.")
            return
        normal_drivers = [d for d in filtered_drivers if d[1] == 0 and (d[2] == 'both' or d[2] == order_type) and (d[3] == 'all' or d[3] == order_route)]
        if normal_drivers:
            await asyncio.gather(*[send_to_driver(d[0], d[4]) for d in normal_drivers], return_exceptions=True)


@router.message(F.chat.type == "private", IsMenuButton('leaderboard'))
async def show_leaderboard(message: types.Message):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    
    is_enabled = await get_setting('leaderboard_enabled', '1') == '1'
    if not is_enabled:
        return await message.answer("⚠️ System disabled.") # Or get_trans(lang, 'feature_disabled')
    
    top_drivers = await get_weekly_leaderboard()
    
    if not top_drivers:
        return await message.answer(get_trans(lang, 'empty_leaderboard'))
    
    text = get_trans(lang, 'weekly_leaderboard_title')
    import html
    for i, (d_id, rides, name) in enumerate(top_drivers):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🔹"
        safe_name = html.escape(name)
        text += f"{medal} {safe_name}: <b>{rides} ta</b>\n"
        
    rank = await get_driver_rank(user_id)
    if rank:
        text += get_trans(lang, 'driver_rank_text').format(rank=rank)
        
    await message.answer(text, parse_mode="HTML")

@router.callback_query(F.data == "driver_stats")
async def driver_stats_handler(callback: types.CallbackQuery):
    lang = await get_user_language(callback.from_user.id)
    await callback.answer(get_trans(lang, 'empty_leaderboard'))

@router.callback_query(F.data.startswith("live_loc_req_"))
async def request_live_loc_flow(callback: types.CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[3])
    lang = await get_user_language(callback.from_user.id)
    await state.update_data(active_live_order_id=order_id)
    await callback.message.answer(get_trans(lang, 'share_loc_instruction'), parse_mode="HTML")
    await callback.answer()

@router.edited_message(F.location)
async def handle_driver_live_loc(message: types.Message, state: FSMContext):
    if not message.location: return
    
    from database.db import update_driver_location
    await update_driver_location(message.from_user.id, message.location.latitude, message.location.longitude)

    if await get_setting('btn_live_location', '1') == '0':
        return
        
    if not message.location.live_period: return
    
    data = await state.get_data()
    order_id = data.get('active_live_order_id')
    if not order_id: return
    
    order = await get_order(order_id)
    if not order or order[11] in ['finished', 'cancelled']: # status check
        return
        
    p_id = order[1]
    live_msg_id = order[15] # live_loc_msg_id column is at index 15
    
    try:
        if not live_msg_id:
            # First time sharing, send new location message to passenger
            p_lang = await get_user_language(p_id)
            sent = await message.bot.send_location(
                p_id, 
                latitude=message.location.latitude, 
                longitude=message.location.longitude,
                live_period=3600 # 1 hour
            )
            await message.bot.send_message(p_id, get_trans(p_lang, 'driver_on_way_live'), parse_mode="HTML")
            await update_order_live_location_msg(order_id, sent.message_id)
        else:
            # Update existing live location
            await message.bot.edit_message_live_location(
                chat_id=p_id,
                message_id=live_msg_id,
                latitude=message.location.latitude,
                longitude=message.location.longitude
            )
    except Exception as e:
        logger.error(f"Live location update error: {e}")

@router.callback_query(F.data == "decline_order")
async def decline_order_handler(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass
    await callback.answer()

@router.callback_query(F.data.startswith("bid_"))
async def start_bidding(callback: types.CallbackQuery, state: FSMContext):
    lang = await get_user_language(callback.from_user.id)
    min_balance = float(await get_setting('min_driver_balance', '20000'))
    
    user = await get_user(callback.from_user.id)
    if not user or user[6] < min_balance:
        await callback.answer(get_trans(lang, 'low_balance_alert').format(min_bal=min_balance), show_alert=True)
        return
        
    order_id = int(callback.data.split("_")[1])
    await state.update_data(bidding_order_id=order_id)
    await state.set_state(DriverStates.entering_bid_amount)
    await callback.message.answer(get_trans(lang, 'enter_bid').format(order_id=order_id), parse_mode="HTML")
    await callback.answer()

@router.message(DriverStates.entering_bid_amount, F.text)
async def process_bid_amount(message: types.Message, state: FSMContext):
    lang = await get_user_language(message.from_user.id)
    try:
        amount = float(message.text.replace(" ", ""))
    except ValueError:
        return await message.answer(get_trans(lang, 'invalid_number') if get_trans(lang, 'invalid_number') else "❌ Iltimos, faqat raqam kiriting.")
        
    data = await state.get_data()
    order_id = data.get('bidding_order_id')
    if not order_id: 
        return await state.clear()

    order = await get_order(order_id)
    # Check if order exists and is still pending
    if not order or order[11] != 'pending': # order[11] is status
        await message.answer("⚠️ Bu buyurtma qabul qilingan yoki bekor qilingan.")
        return await state.clear()

    await add_bid(order_id, message.from_user.id, amount)
    p_id = order[1]
    p_lang = await get_user_language(p_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ {amount:,} {get_trans(p_lang, 'accept')}", callback_data=f"ab_{message.from_user.id}_{order_id}_{int(amount)}")],
        [InlineKeyboardButton(text="❌", callback_data=f"rb_{message.from_user.id}_{order_id}")]
    ])
    try:
        await message.bot.send_message(p_id, get_trans(p_lang, 'new_bid_passenger').format(order_id=order_id, amount=amount), reply_markup=kb, parse_mode="HTML")
        await message.answer(get_trans(lang, 'bid_sent'))
    except Exception as e:
        logger.error(f"Failed to send bid to passenger: {e}")
        await message.answer("❌ Xatolik yuz berdi (Mijozga xabar bormadi).")
    
    await state.clear()

@router.callback_query(F.data.regexp(r"^accept_\d+$"))
async def process_accept_order(callback: types.CallbackQuery, state: FSMContext):
    driver_id = callback.from_user.id
    order_id = int(callback.data.split("_")[1])
    lang = await get_user_language(driver_id)
    is_group = callback.message.chat.type in ('group', 'supergroup', 'channel')

    # Check if user is a registered & approved driver
    driver = await get_driver(driver_id)
    if not driver:
        bot_info = BOT_INFO_CACHE or await callback.bot.get_me()
        deep_link = f"https://t.me/{bot_info.username}?start=order_{order_id}"
        try:
            # Telegram automatically opens the bot and triggers /start order_{order_id}
            await callback.answer(url=deep_link)
            return
        except Exception:
            await callback.answer(
                "⚠️ Siz haydovchi sifatida ro'yxatdan o'tmagansiz!\nBotga kiring va ro'yxatdan o'ting.",
                show_alert=True
            )
            return

    if driver[7] != 1:  # is_approved
        bot_info = BOT_INFO_CACHE or await callback.bot.get_me()
        try:
            await callback.answer(url=f"https://t.me/{bot_info.username}?start=profile")
            return
        except Exception:
            await callback.answer("⏳ Hujjatlaringiz admin tomonidan hali tasdiqlanmagan.", show_alert=True)
            return


    success, msg = await accept_order(order_id, driver_id)
    if success:
        acc_text = get_trans(lang, 'order_accepted_driver').format(order_id=order_id)
        acc_text += f"\n\n{get_trans(lang, 'driver_warning_accept')}"

        if is_group:
            # In group: answer with alert, edit message to show taken status
            await callback.answer(f"✅ Buyurtma #{order_id} qabul qilindi!", show_alert=True)
            try:
                taken_text = (
                    f"✅ <b>BUYURTMA QABUL QILINDI!</b>\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"🔢 <b>Buyurtma:</b> <code>#{order_id}</code>\n"
                    f"👤 <b>Haydovchi:</b> {callback.from_user.full_name}\n"
                    f"⏱ <b>Vaqt:</b> {datetime.now().strftime('%H:%M')}\n"
                    f"<i>Bu buyurtma endi mavjud emas.</i>"
                )
                if callback.message.photo or callback.message.caption:
                    await callback.message.edit_caption(caption=taken_text, reply_markup=None, parse_mode="HTML")
                else:
                    await callback.message.edit_text(taken_text, reply_markup=None, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error editing group message after accept: {e}")
        else:
            # In private: edit message normally
            try:
                if callback.message.photo or callback.message.caption:
                    await callback.message.edit_caption(caption=acc_text, parse_mode="HTML")
                else:
                    await callback.message.edit_text(acc_text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error editing message after acceptance: {e}")
                await callback.message.answer(acc_text, parse_mode="HTML")

        # Notify passenger
        order = await get_order(order_id)
        if order:
            p_id = order[1]
            p_lang = await get_user_language(p_id)
            d_info, u_info = await get_driver(driver_id), await get_user(driver_id)
            import html
            safe_name = html.escape(u_info[1])
            safe_car = html.escape(d_info[1])
            text = get_trans(p_lang, 'order_found_passenger').format(
                name=safe_name,
                phone=u_info[2],
                car=safe_car,
                plate=d_info[2]
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚨 SOS", callback_data="sos_alert")]
            ])
            try:
                await callback.bot.send_message(p_id, text, reply_markup=kb, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error notifying passenger {p_id}: {e}")

        # Send driver management keyboard (only in private chat)
        if not is_group:
            kb_list = []
            kb_list.append([InlineKeyboardButton(text=get_trans(lang, 'arrived'), callback_data=f"status_arrived_{order_id}")])
            kb_list.append([InlineKeyboardButton(text=get_trans(lang, 'finish'), callback_data=f"status_finished_{order_id}")])
            if await get_setting('btn_live_location', '1') == '1':
                kb_list.append([InlineKeyboardButton(text=get_trans(lang, 'share_live_location'), callback_data=f"live_loc_req_{order_id}")])
            if await get_setting('btn_chat', '1') == '1':
                kb_list.append([InlineKeyboardButton(text=get_trans(lang, 'chat_btn'), callback_data=f"chat_{order_id}")])
            kb_list.append([InlineKeyboardButton(text="🚨 SOS", callback_data="sos_alert")])
            kb = InlineKeyboardMarkup(inline_keyboard=kb_list)
            await callback.message.answer(get_trans(lang, 'active_order_manage'), reply_markup=kb)
        else:
            # In group: send private message to driver with management buttons
            try:
                kb_list = [
                    [InlineKeyboardButton(text=get_trans(lang, 'arrived'), callback_data=f"status_arrived_{order_id}")],
                    [InlineKeyboardButton(text=get_trans(lang, 'finish'), callback_data=f"status_finished_{order_id}")],
                    [InlineKeyboardButton(text="🚨 SOS", callback_data="sos_alert")]
                ]
                kb = InlineKeyboardMarkup(inline_keyboard=kb_list)
                await callback.bot.send_message(
                    driver_id,
                    f"✅ <b>Buyurtma #{order_id} qabul qilindi!</b>\n{acc_text}",
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error sending private message to driver {driver_id} after group accept: {e}")
    else:
        # Order already taken or other error
        if "Tarif" in msg or "Pochta" in msg or "Kvota" in msg:
            await callback.answer("❌ Faol tarif yo'q!", show_alert=True)
            if not is_group:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Tarif sotib olish", callback_data="driver_tariffs")]
                ])
                await callback.message.answer(
                    f"⚠️ <b>{msg}</b>\n\nBuyurtma qabul qilish uchun avval tarif sotib oling:",
                    reply_markup=kb, parse_mode="HTML"
                )
        elif "allaqachon" in msg.lower() or "taken" in msg.lower() or "qabul" in msg.lower():
            await callback.answer("⚡️ Bu buyurtma allaqachon boshqa haydovchi tomonidan qabul qilindi!", show_alert=True)
            if is_group:
                try:
                    await callback.message.edit_text(
                        f"⚡️ <b>Buyurtma allaqachon qabul qilindi!</b>\n<i>Vaqtida ulgurmadingiz.</i>",
                        reply_markup=None, parse_mode="HTML"
                    )
                except:
                    pass
        else:
            await callback.answer(msg, show_alert=True)
            if not is_group:
                try:
                    await callback.message.delete()
                except:
                    pass



@router.callback_query(F.data.startswith("status_"))
async def handle_status_update(callback: types.CallbackQuery):
    parts = callback.data.split("_", 2)  # maxsplit=2: ["status", "arrived", "123"]
    _, status, order_id = parts
    order_id = int(order_id)
    lang = await get_user_language(callback.from_user.id)
    
    await update_order_status(order_id, status)
    await callback.answer("✅ Muvaffaqiyatli yangilandi!")
    
    order = await get_order(order_id)
    if order:
        p_id = order[1]
        p_lang = await get_user_language(p_id)
        if status == "arrived":
            await callback.bot.send_message(p_id, get_trans(p_lang, 'driver_arrived'), parse_mode="HTML")
        elif status == "finished":
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⭐", callback_data=f"rate_1_{order_id}"),
                 InlineKeyboardButton(text="⭐⭐", callback_data=f"rate_2_{order_id}"),
                 InlineKeyboardButton(text="⭐⭐⭐", callback_data=f"rate_3_{order_id}"),
                 InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data=f"rate_4_{order_id}"),
                 InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data=f"rate_5_{order_id}")]
            ])
            await callback.bot.send_message(p_id, get_trans(p_lang, 'order_finished_passenger'), reply_markup=kb, parse_mode="HTML")
            try:
                if callback.message.photo or callback.message.caption:
                    await callback.message.edit_caption(caption=get_trans(lang, 'order_finished_driver').format(order_id=order_id), parse_mode="HTML")
                else:
                    await callback.message.edit_text(get_trans(lang, 'order_finished_driver').format(order_id=order_id), parse_mode="HTML")
            except:
                await callback.message.answer(get_trans(lang, 'order_finished_driver').format(order_id=order_id), parse_mode="HTML")

@router.message(F.chat.type == "private", F.text.in_({"📋 Buyurtmalarim", "📋 Мои заказы", "📋 My Orders", "📋 Faol buyurtmalar"}))
async def show_my_orders(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    user = await get_user(user_id)
    if not user: return
    
    lang = user[8] or 'uz'
    role = user[4]
    
    from database.db import get_user_orders_history
    orders = await get_user_orders_history(user_id, role, limit=5)
    
    if not orders:
        return await message.answer(get_trans(lang, 'no_active_orders'))
        
    await message.answer(get_trans(lang, 'my_orders_title'), parse_mode="HTML")
    
    for order in orders:
        # order: order_id(0), p_id(1), d_id(2), from(3), to(4), price(5), pax(6), time(7), ts(8), f_lat(9), f_lon(10), status(11), class(12), type(13), photo(14)
        order_id = order[0]
        status = order[11]
        o_date = order[7] if (len(order) > 7 and order[7]) else (order[16][:16] if (len(order) > 16 and order[16]) else "Noma'lum")
        
        status_map = {
            'pending': "⏳ Kutilmoqda",
            'accepted': "✅ Qabul qilingan",
            'arrived': "🚶 Haydovchi kelgan",
            'finished': "🏁 Tugatilgan",
            'cancelled': "❌ Bekor qilingan"
        }
        status_text = status_map.get(status, status)
        
        # Safe price formatting
        try:
            price_val = float(order[5]) if order[5] is not None else 0
            price_text = f"{int(price_val):,} so'm"
        except (ValueError, TypeError):
            price_text = f"{order[5]} so'm"
            
        text = (
            f"🆔 <b>Buyurtma #{order_id}</b>\n"
            f"📅 Sana: <code>{o_date}</code>\n"
            f"📍 {order[3]} ➔ {order[4]}\n"
            f"💰 {price_text} | {status_text}"
        )
        
        kb_list = []
        if status in ['accepted', 'arrived']:
            kb_list.append([InlineKeyboardButton(text=get_trans(lang, 'chat_btn'), callback_data=f"chat_{order_id}")])
            if role == 'passenger':
                kb_list.append([InlineKeyboardButton(text=get_trans(lang, 'cancel'), callback_data=f"cancel_order_{order_id}")])
            else:
                kb_list.append([InlineKeyboardButton(text=get_trans(lang, 'finish'), callback_data=f"status_finished_{order_id}")])
        
        kb = InlineKeyboardMarkup(inline_keyboard=kb_list) if kb_list else None
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

    # Add export button
    export_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_trans(lang, 'download_history_btn'), callback_data="export_my_history")]
    ])
    await message.answer(get_trans(lang, 'download_history_hint'), reply_markup=export_kb)

@router.callback_query(F.data == "export_my_history")
async def export_my_history_handler(callback: types.CallbackQuery, bot: Bot):
    await callback.answer(get_trans('uz', 'loading_info') if callback.from_user.language_code != 'uz' else "⏳ Yuklanmoqda...")
    user_id = callback.from_user.id
    user = await get_user(user_id)
    lang = user[8] if user else 'uz'
    role = user[4] if user else 'passenger'
    
    from database.db import get_user_full_order_history
    orders = await get_user_full_order_history(user_id, role)
    
    if not orders:
        return await callback.message.answer(get_trans(lang, 'no_active_orders'))
        
    role_text = "YO'LOVCHI" if role == 'passenger' else "HAYDOVCHI"
    import os
    file_path = f"history_{user_id}.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"--- BUYURTMALAR TARIXI ({role_text}) ---\n\n")
        for o in orders:
            # order: order_id(0), p_id(1), d_id(2), from(3), to(4), price(5), pax(6), time(7), notified(8) ... timestamp(16)
            o_dt = o[7] if (len(o) > 7 and o[7]) else (o[16][:16] if (len(o) > 16 and o[16]) else "Noma'lum")
            line = f"#{o[0]} | {o_dt} | {o[3]} -> {o[4]} | {o[5]:,} so'm | {o[11]}\n"
            f.write(line)
            
    try:
        from aiogram.types import FSInputFile
        doc = FSInputFile(file_path)
        await bot.send_document(
            chat_id=user_id,
            document=doc,
            caption=get_trans(lang, 'history_file_caption').format(count=len(orders)),
            parse_mode="HTML"
        )
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@router.message(F.chat.type == "private", IsMenuButton('route_settings'))
async def show_route_settings(message: types.Message):
    lang = await get_user_language(message.from_user.id)
    driver = await get_driver(message.from_user.id)
    curr_route = driver[12] if driver and len(driver) > 12 and driver[12] else 'all'
    curr_work = driver[13] if driver and len(driver) > 13 and driver[13] else 'both'
    
    route_names = {
        'all': 'Barcha yo\'nalishlar',
        'toshkent-qashqadaryo': 'Toshkent ➡️ Qashqadaryo',
        'qashqadaryo-toshkent': 'Qashqadaryo ➡️ Toshkent',
        'intra': 'Viloyat ichida'
    }
    work_names = {
        'taxi': 'Faqat Taksi',
        'parcel': 'Faqat Pochta',
        'both': 'Ikkalasi ham'
    }
    
    display_route = route_names.get(curr_route, curr_route)
    display_work = work_names.get(curr_work, curr_work)
    
    text = (
        "<b>🛣 YO'NALISH VA ISH TURI SOZLAMALARI</b>\n\n"
        f"📍 Hozirgi yo'nalish: <b>{display_route}</b>\n"
        f"💼 Hozirgi ish turi: <b>{display_work}</b>\n\n"
        "O'zgartirish uchun quyidagilardan birini tanlang:"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺 Yo'nalishni o'zgartirish", callback_data="show_routes")],
        [InlineKeyboardButton(text="💼 Ish turini o'zgartirish", callback_data="show_work_types")],
        [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_profile")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "show_routes")
async def show_routes_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 Barcha yo'nalishlar", callback_data="set_route_all")],
        [InlineKeyboardButton(text="🏙 Toshkent ➡️ Qashqadaryo", callback_data="set_route_toshkent-qashqadaryo")],
        [InlineKeyboardButton(text="🏕 Qashqadaryo ➡️ Toshkent", callback_data="set_route_qashqadaryo-toshkent")],
        [InlineKeyboardButton(text="🔄 Viloyat ichida", callback_data="set_route_intra")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="back_to_route_settings")]
    ])
    await callback.message.edit_text("<b>🛣 Yo'nalishni tanlang:</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "show_work_types")
async def show_work_types_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚕 Faqat Taksi", callback_data="set_work_taxi")],
        [InlineKeyboardButton(text="📦 Faqat Pochta", callback_data="set_work_parcel")],
        [InlineKeyboardButton(text="🔄 Ikkalasi ham", callback_data="set_work_both")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="back_to_route_settings")]
    ])
    await callback.message.edit_text("<b>💼 Ish turini tanlang:</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "back_to_route_settings")
async def back_to_route_settings(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass
    await show_route_settings(callback.message)

@router.message(F.chat.type == "private", IsMenuButton('available_parcels'))
async def show_available_parcels(message: types.Message):
    from database.db import get_pending_parcels
    lang = await get_user_language(message.from_user.id)
    parcels = await get_pending_parcels()
    
    if not parcels:
        return await message.answer("📭 Hozircha mavjud pochtalar yo'q.")
        
    await message.answer(get_trans(lang, 'available_parcels_title'), parse_mode="HTML")
    
    for p in parcels:
        order_id = p[0]
        from_loc = p[3]
        to_loc = p[4]
        price = p[5]
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_trans(lang, 'accept'), callback_data=f"accept_{order_id}")]
        ])
        
        text = f"📦 <b>Buyurtma #{order_id}</b>\n📍 {from_loc} ➔ {to_loc}\n💰 {price:,} so'm"
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(F.chat.type == "private", F.location)
async def handle_driver_location(message: types.Message):
    from database.db import update_driver_location, get_user
    user = await get_user(message.from_user.id)
    if not user or user[4] != 'driver':
        return
        
    lat = message.location.latitude
    lon = message.location.longitude
    await update_driver_location(message.from_user.id, lat, lon)
    
    # Optional: Silently confirm for live location updates
    if not message.edited_at and not getattr(message.location, 'live_period', None):
        await message.answer("✅ Joylashuvingiz yangilandi. Endi yo'lovchilar sizni radarda ko'rishlari mumkin.")
        # We need to refresh the driver menu or settings after location update
        lang = await get_user_language(message.from_user.id)
        driver = await get_driver(message.from_user.id)
        curr_route = driver[12] if driver and len(driver) > 12 and driver[12] else 'all'
        curr_work = driver[13] if driver and len(driver) > 13 and driver[13] else 'both'
        
@router.message(F.chat.type == "private", IsMenuButton('route_settings'))
@router.message(F.chat.type == "private", F.text.in_({"🛣 Yo'nalish sozlamasi", "🛣 Настройки маршрута", "🛣 Yo'nalish sozlash", "/route"}))
async def open_route_settings(message: types.Message):
    lang = await get_user_language(message.from_user.id)
    driver = await get_driver(message.from_user.id)
    if not driver:
        return await message.answer("⚠️ Ushbu sozlama faqat haydovchilar uchun.")
        
    curr_route = driver[12] if driver and len(driver) > 12 and driver[12] else 'all'
    curr_work = driver[13] if driver and len(driver) > 13 and driver[13] else 'both'
    
    route_names = {
        'all': 'Barcha yo\'nalishlar 🌐',
        'toshkent-qashqadaryo': 'Toshkent ➡️ Qashqadaryo',
        'qashqadaryo-toshkent': 'Qashqadaryo ➡️ Toshkent',
        'intra': 'Viloyat ichida 🏘'
    }
    work_names = {
        'taxi': 'Faqat Taksi 🚕',
        'parcel': 'Faqat Pochta 📦',
        'both': 'Ikkalasi ham (Taksi + Pochta) 🚀'
    }
    
    display_route = route_names.get(curr_route, curr_route)
    display_work = work_names.get(curr_work, curr_work)
    
    text = (
        "<b>🛣 YO'NALISH VA ISH TURI SOZLAMALARI</b>\n━━━━━━━━━━━━━━\n\n"
        f"📍 <b>Hozirgi yo'nalish:</b> {display_route}\n"
        f"💼 <b>Hozirgi ish turi:</b> {display_work}\n\n"
        "Qaysi buyurtmalarni qabul qilmoqchisiz? Quyidagilardan birini tanlang:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺 Yo'nalishni o'zgartirish", callback_data="show_routes")],
        [InlineKeyboardButton(text="💼 Ish turini o'zgartirish", callback_data="show_work_types")],
        [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_profile")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "show_routes")
async def show_routes_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Barcha yo'nalishlar", callback_data="set_route_all")],
        [InlineKeyboardButton(text="➡️ Toshkent ➔ Qashqadaryo", callback_data="set_route_toshkent-qashqadaryo")],
        [InlineKeyboardButton(text="⬅️ Qashqadaryo ➔ Toshkent", callback_data="set_route_qashqadaryo-toshkent")],
        [InlineKeyboardButton(text="🏘 Faqat viloyat ichida", callback_data="set_route_intra")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="route_settings_back")]
    ])
    await callback.message.edit_text("<b>🗺 Qaysi yo'nalishda qatnaysiz?</b>\nKerakli yo'nalishni tanlang:", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "show_work_types")
async def show_work_types_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚕 Faqat Taksi", callback_data="set_work_taxi")],
        [InlineKeyboardButton(text="📦 Faqat Pochta", callback_data="set_work_parcel")],
        [InlineKeyboardButton(text="🚀 Ikkalasi ham (Taksi + Pochta)", callback_data="set_work_both")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="route_settings_back")]
    ])
    await callback.message.edit_text("<b>💼 Ish turini tanlang:</b>", reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "route_settings_back")
async def process_route_settings_back(callback: types.CallbackQuery):
    driver = await get_driver(callback.from_user.id)
    lang = await get_user_language(callback.from_user.id)
    curr_route = driver[12] if driver and len(driver) > 12 and driver[12] else 'all'
    curr_work = driver[13] if driver and len(driver) > 13 and driver[13] else 'both'
    
    route_names = {
        'all': 'Barcha yo\'nalishlar 🌐',
        'toshkent-qashqadaryo': 'Toshkent ➡️ Qashqadaryo',
        'qashqadaryo-toshkent': 'Qashqadaryo ➡️ Toshkent',
        'intra': 'Viloyat ichida 🏘'
    }
    work_names = {
        'taxi': 'Faqat Taksi 🚕',
        'parcel': 'Faqat Pochta 📦',
        'both': 'Ikkalasi ham (Taksi + Pochta) 🚀'
    }
    
    text = (
        "<b>🛣 YO'NALISH VA ISH TURI SOZLAMALARI</b>\n━━━━━━━━━━━━━━\n\n"
        f"📍 <b>Hozirgi yo'nalish:</b> {route_names.get(curr_route, curr_route)}\n"
        f"💼 <b>Hozirgi ish turi:</b> {work_names.get(curr_work, curr_work)}\n\n"
        "Qaysi buyurtmalarni qabul qilmoqchisiz? Quyidagilardan birini tanlang:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺 Yo'nalishni o'zgartirish", callback_data="show_routes")],
        [InlineKeyboardButton(text="💼 Ish turini o'zgartirish", callback_data="show_work_types")],
        [InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_profile")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("set_work_"))
async def process_work_type_selection(callback: types.CallbackQuery):
    from database.db import set_driver_work_type
    work_type = callback.data.replace("set_work_", "")
    await set_driver_work_type(callback.from_user.id, work_type)
    
    labels = {'taxi': 'Faqat Taksi 🚕', 'parcel': 'Faqat Pochta 📦', 'both': 'Ikkalasi ham 🚀'}
    await callback.message.edit_text(f"✅ Ish turi muvaffaqiyatli saqlandi: <b>{labels.get(work_type)}</b>", parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("set_route_"))
async def process_route_selection(callback: types.CallbackQuery):
    route = callback.data.replace("set_route_", "")
    await set_driver_route(callback.from_user.id, route)
    
    route_names = {
        'all': 'Barcha yo\'nalishlar 🌐',
        'toshkent-qashqadaryo': 'Toshkent ➡️ Qashqadaryo',
        'qashqadaryo-toshkent': 'Qashqadaryo ➡️ Toshkent',
        'intra': 'Viloyat ichida 🏘'
    }
    
    await callback.message.edit_text(
        f"✅ Yo'nalish muvaffaqiyatli saqlandi:\n<b>{route_names.get(route, route)}</b>",
        parse_mode="HTML"
    )
    await callback.answer()

# --- 📦 MAVJUD POCHTALAR RO'YXATI ---
@router.message(F.chat.type == "private", IsMenuButton('available_parcels'))
@router.message(F.chat.type == "private", F.text.in_({"📦 Mavjud pochtalar", "📦 Доступные посылки", "📦 Available Parcels", "/parcels"}))
async def show_available_parcels(message: types.Message):
    user_id = message.from_user.id
    driver = await get_driver(user_id)
    lang = await get_user_language(user_id)
    
    if not driver:
        return await message.answer("⚠️ Ushbu bo'lim faqat ro'yxatdan o'tgan haydovchilar uchun.")
        
    from database.db import get_pending_parcels
    parcels = await get_pending_parcels(limit=6)
    
    if not parcels:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Yangilash", callback_data="refresh_parcels")]
        ])
        return await message.answer(
            "<b>📦 MAVJUD POCHTALA RO'YXATI</b>\n━━━━━━━━━━━━━━\n\n"
            "Hozirda kutilayotgan pochta buyurtmalari yo'q.\nYangi pochta tushsa sizga xabar beriladi! 🔔",
            reply_markup=kb, parse_mode="HTML"
        )
        
    await message.answer("<b>📦 HOZIRDA MAVJUD POCHTALA RO'YXATI:</b>\n━━━━━━━━━━━━━━", parse_mode="HTML")
    
    for p in parcels:
        order_id, from_l, to_l, price, ts, photo = p
        p_text = (
            f"📦 <b>Pochta #{order_id}</b>\n"
            f"📍 <b>Qayerdan:</b> {from_l}\n"
            f"🏁 <b>Qayerga:</b> {to_l}\n"
            f"💰 <b>Narxi:</b> <b>{int(price):,} so'm</b>\n"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Qabul qilish", callback_data=f"accept_{order_id}")],
            [InlineKeyboardButton(text="💰 Boshqa narx taklif qilish", callback_data=f"bid_driver_{order_id}")]
        ])
        if photo:
            try:
                await message.answer_photo(photo, caption=p_text, reply_markup=kb, parse_mode="HTML")
            except:
                await message.answer(p_text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(p_text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "refresh_parcels")
async def refresh_parcels_cb(callback: types.CallbackQuery):
    await callback.answer("Yangilandi 🔄")
    try:
        await callback.message.delete()
    except:
        pass
    await show_available_parcels(callback.message)


# ==========================================
# 💺 HAMROH REYSLARI (HAYDOVCHI TOMONI)
# ==========================================

from utils.states import RideStates, ReturnTripStates
from utils.route_helper import get_location_keyboard
from database.db import (
    create_ride, get_driver_active_rides, get_ride_bookings, cancel_ride, 
    set_driver_return_trip, close_return_trip
)
from aiogram.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton

@router.message(F.chat.type == "private", IsMenuButton('create_ride_btn'))
@router.message(F.chat.type == "private", F.text.in_({"➕ Reys e'lon qilish", "➕ Создать рейс", "/create_ride"}))
async def start_create_ride(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    driver = await get_driver(user_id)
    lang = await get_user_language(user_id)
    
    if not driver:
        return await message.answer("⚠️ Reys e'lon qilish faqat ro'yxatdan o'tgan haydovchilar uchun.")
        
    if driver[7] != 1: # is_approved
        return await message.answer("⏳ Hujjatlaringiz hali admin tomonidan tasdiqlanmagan.")
        
    await state.clear()
    await state.set_state(RideStates.entering_from)
    
    kb = await get_location_keyboard("from", user_id, lang=lang, prefix="d_ride_loc_")
    await message.answer(
        "<b>💺 YANGI REYS E'LON QILISH (Hamroh / Poputchik)</b>\n━━━━━━━━━━━━━━\n"
        "1️⃣ <b>Qayerdan yo'lga chiqasiz?</b>\nQuyidagi ro'yxatdan tanlang yoki yozing:",
        reply_markup=kb, parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("d_ride_loc_from_"))
async def process_driver_ride_from(callback: types.CallbackQuery, state: FSMContext):
    place = callback.data.replace("d_ride_loc_from_", "")
    lang = await get_user_language(callback.from_user.id)
    
    if place == "none" or place == "back":
        return await callback.answer()
        
    if place == "custom":
        await callback.message.edit_text("✏️ <b>Qayerdan yo'lga chiqasiz?</b>\n<i>Manzilni yozing:</i>", parse_mode="HTML")
        await state.set_state(RideStates.entering_from)
        return await callback.answer()
        
    await state.update_data(ride_from=place)
    await state.set_state(RideStates.entering_to)
    
    kb = await get_location_keyboard("to", callback.from_user.id, lang=lang, prefix="d_ride_loc_")
    await callback.message.edit_text(
        f"🔴 Qayerdan: <b>{place}</b>\n\n"
        f"2️⃣ <b>Qayerga borasiz?</b> (Manzilni tanlang):",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()

@router.message(RideStates.entering_from, F.text)
async def process_driver_ride_from_text(message: types.Message, state: FSMContext):
    place = message.text.strip()
    lang = await get_user_language(message.from_user.id)
    await state.update_data(ride_from=place)
    await state.set_state(RideStates.entering_to)
    
    kb = await get_location_keyboard("to", message.from_user.id, lang=lang, prefix="d_ride_loc_")
    await message.answer(
        f"🔴 Qayerdan: <b>{place}</b>\n\n"
        f"2️⃣ <b>Qayerga borasiz?</b> (Manzilni tanlang):",
        reply_markup=kb, parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("d_ride_loc_to_"))
async def process_driver_ride_to(callback: types.CallbackQuery, state: FSMContext):
    place = callback.data.replace("d_ride_loc_to_", "")
    if place == "none" or place == "back":
        return await callback.answer()
        
    if place == "custom":
        await callback.message.edit_text("✏️ <b>Qayerga borasiz?</b>\n<i>Manzilni yozing:</i>", parse_mode="HTML")
        await state.set_state(RideStates.entering_to)
        return await callback.answer()
        
    await state.update_data(ride_to=place)
    await state.set_state(RideStates.entering_time)
    
    kb_time = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Bugun 15:00"), KeyboardButton(text="Bugun 18:00")],
        [KeyboardButton(text="Ertaga 06:00"), KeyboardButton(text="Ertaga 08:00")],
        [KeyboardButton(text="❌ Bekor qilish")]
    ], resize_keyboard=True, one_time_keyboard=True)
    
    await callback.message.delete()
    await callback.message.answer(
        f"🏁 Qayerga: <b>{place}</b>\n\n"
        f"3️⃣ <b>Jo'nash vaqti va sanasini kiriting:</b>\n"
        f"<i>(Masalan: <code>Ertaga 07:00</code> yoki <code>Bugun 17:30</code>)</i>",
        reply_markup=kb_time, parse_mode="HTML"
    )
    await callback.answer()

@router.message(RideStates.entering_to, F.text)
async def process_driver_ride_to_text(message: types.Message, state: FSMContext):
    place = message.text.strip()
    await state.update_data(ride_to=place)
    await state.set_state(RideStates.entering_time)
    
    kb_time = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Bugun 15:00"), KeyboardButton(text="Bugun 18:00")],
        [KeyboardButton(text="Ertaga 06:00"), KeyboardButton(text="Ertaga 08:00")],
        [KeyboardButton(text="❌ Bekor qilish")]
    ], resize_keyboard=True, one_time_keyboard=True)
    
    await message.answer(
        f"🏁 Qayerga: <b>{place}</b>\n\n"
        f"3️⃣ <b>Jo'nash vaqti va sanasini kiriting:</b>\n"
        f"<i>(Masalan: <code>Ertaga 07:00</code> yoki <code>Bugun 17:30</code>)</i>",
        reply_markup=kb_time, parse_mode="HTML"
    )

@router.message(RideStates.entering_time, F.text)
async def process_driver_ride_time(message: types.Message, state: FSMContext):
    if "bekor qilish" in message.text.lower():
        await state.clear()
        lang = await get_user_language(message.from_user.id)
        return await message.answer("❌ Bekor qilindi.", reply_markup=await get_driver_menu(is_online=True, lang=lang))
        
    dep_time = message.text.strip()
    await state.update_data(ride_time=dep_time)
    await state.set_state(RideStates.entering_seats)
    
    kb_seats = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="4 ta joy"), KeyboardButton(text="3 ta joy")],
        [KeyboardButton(text="2 ta joy"), KeyboardButton(text="1 ta joy")]
    ], resize_keyboard=True, one_time_keyboard=True)
    
    await message.answer(
        f"⏰ Vaqt: <b>{dep_time}</b>\n\n"
        f"4️⃣ <b>Nechta bo'sh o'rindiq bor?</b>",
        reply_markup=kb_seats, parse_mode="HTML"
    )

@router.message(RideStates.entering_seats, F.text)
async def process_driver_ride_seats(message: types.Message, state: FSMContext):
    text = message.text.replace("ta joy", "").replace("ta", "").strip()
    try:
        seats = int(text)
        if seats < 1 or seats > 8:
            seats = 4
    except:
        seats = 4
        
    await state.update_data(ride_seats=seats)
    await state.set_state(RideStates.entering_price)
    
    kb_prices = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="100 000"), KeyboardButton(text="120 000")],
        [KeyboardButton(text="150 000"), KeyboardButton(text="50 000")]
    ], resize_keyboard=True, one_time_keyboard=True)
    
    await message.answer(
        f"💺 Bo'sh joylar: <b>{seats} ta</b>\n\n"
        f"5️⃣ <b>1 ta o'rindiq (kishi) uchun narxni kiriting:</b> (so'mda)\n"
        f"<i>(Masalan: <code>120 000</code>)</i>",
        reply_markup=kb_prices, parse_mode="HTML"
    )

@router.message(RideStates.entering_price, F.text)
async def process_driver_ride_price(message: types.Message, state: FSMContext):
    raw_p = message.text.replace(" ", "").replace("so'm", "").replace("som", "").strip()
    try:
        price = float(raw_p)
        if price < 5000:
            price = 50000
    except:
        price = 100000
        
    await state.update_data(ride_price=price)
    await state.set_state(RideStates.entering_notes)
    
    kb_skip = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="O'tkazib yuborish ➡️")],
        [KeyboardButton(text="Konditsioner bor ❄️, Yukxona bo'sh 🧳")]
    ], resize_keyboard=True, one_time_keyboard=True)
    
    await message.answer(
        f"💰 Narxi: <b>{int(price):,} so'm / joy</b>\n\n"
        f"6️⃣ <b>Qo'shimcha izoh yoki qulayliklar bormi?</b> (Ixtiyoriy)",
        reply_markup=kb_skip, parse_mode="HTML"
    )

@router.message(RideStates.entering_notes, F.text)
async def process_driver_ride_notes(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    driver = await get_driver(user_id)
    lang = await get_user_language(user_id)
    
    notes = "" if "o'tkazib" in message.text.lower() else message.text.strip()
    data = await state.get_data()
    
    from_loc = data.get('ride_from', 'Chiroqchi')
    to_loc = data.get('ride_to', 'Toshkent')
    dep_time = data.get('ride_time', 'Hozir')
    seats = data.get('ride_seats', 4)
    price = data.get('ride_price', 100000)
    
    car_model = driver[1] if driver else "Avtomobil"
    car_plate = driver[2] if driver else "---"
    
    ride_id = await create_ride(
        driver_id=user_id,
        from_location=from_loc,
        to_location=to_loc,
        departure_time=dep_time,
        total_seats=seats,
        price_per_seat=price,
        car_model=car_model,
        car_number=car_plate,
        notes=notes
    )
    
    await state.clear()
    
    confirm_text = (
        f"🎉 <b>REYSINGIZ E'LON QILINDI!</b> (ID: #{ride_id})\n"
        f"━━━━━━━━━━━━━━\n"
        f"📍 <b>Yo'nalish:</b> {from_loc} ➡️ {to_loc}\n"
        f"⏰ <b>Jo'nash:</b> {dep_time}\n"
        f"💺 <b>Bo'sh joylar:</b> {seats} ta\n"
        f"💰 <b>Narxi:</b> <b>{int(price):,} so'm</b> / joy\n"
        f"🚘 <b>Mashina:</b> {car_model} ({car_plate})\n"
    )
    if notes:
        confirm_text += f"💬 <b>Izoh:</b> {notes}\n"
        
    confirm_text += (
        f"━━━━━━━━━━━━━━\n"
        f"✅ Yo'lovchilar joy band qilganda sizga darhol telefon raqami bilan xabar beramiz!"
    )
    
    await message.answer(confirm_text, reply_markup=await get_driver_menu(is_online=True, lang=lang), parse_mode="HTML")
    
    # Broadcast to channels/groups
    try:
        bot_info = await message.bot.get_me()
        group_text = (
            f"💺 <b>YANGI HAMROH / SHAQARLARARO REYS!</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"📍 <b>Yo'nalish:</b> {from_loc} ➡️ {to_loc}\n"
            f"⏰ <b>Vaqt:</b> {dep_time}\n"
            f"💺 <b>Bo'sh joylar:</b> {seats} ta\n"
            f"💰 <b>Narxi:</b> <b>{int(price):,} so'm</b>/kishi\n"
            f"🚘 <b>Mashina:</b> {car_model}\n"
            f"━━━━━━━━━━━━━━\n"
            f"👉 Joyni band qilish uchun botga kiring:"
        )
        group_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💺 Joy band qilish", url=f"https://t.me/{bot_info.username}?start=rides")]
        ])
        group_ids = await get_order_channels(order_type='taxi')
        if group_ids:
            for g_id in group_ids:
                try:
                    await message.bot.send_message(g_id, group_text, reply_markup=group_kb, parse_mode="HTML")
                except:
                    pass
    except Exception as e:
        logger.error(f"Error broadcasting ride: {e}")

# ==========================================
# 🔄 POPUTKA / QAYTISHGA YO'LOVCHI
# ==========================================

@router.message(F.chat.type == "private", IsMenuButton('return_trip_btn'))
@router.message(F.chat.type == "private", F.text.in_({"🔄 Qaytishga yo'lovchi", "🔄 Обратный попутчик", "/return_trip"}))
async def start_return_trip(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    driver = await get_driver(user_id)
    lang = await get_user_language(user_id)
    
    if not driver:
        return await message.answer("⚠️ Bu bo'lim faqat haydovchilar uchun.")
        
    await state.clear()
    await state.set_state(ReturnTripStates.entering_from)
    
    kb = await get_location_keyboard("from", user_id, lang=lang, prefix="ret_loc_")
    await message.answer(
        "<b>🔄 BO'SH QAYTMASLIK / POPUTKA REJIMI</b>\n━━━━━━━━━━━━━━\n"
        "Qaysi shahardan orqaga qaytayapsiz? (Boshlang'ich nuqtani tanlang):",
        reply_markup=kb, parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("ret_loc_from_"))
async def process_ret_from(callback: types.CallbackQuery, state: FSMContext):
    place = callback.data.replace("ret_loc_from_", "")
    lang = await get_user_language(callback.from_user.id)
    if place == "none" or place == "back": return await callback.answer()
    
    await state.update_data(ret_from=place)
    await state.set_state(ReturnTripStates.entering_to)
    
    kb = await get_location_keyboard("to", callback.from_user.id, lang=lang, prefix="ret_loc_")
    await callback.message.edit_text(
        f"🔴 Qayerdan qaytasiz: <b>{place}</b>\n\n"
        f"Qayerga qaytmoqchisiz? (Manzilni tanlang):",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("ret_loc_to_"))
async def process_ret_to(callback: types.CallbackQuery, state: FSMContext):
    place = callback.data.replace("ret_loc_to_", "")
    if place == "none" or place == "back": return await callback.answer()
    
    await state.update_data(ret_to=place)
    await state.set_state(ReturnTripStates.entering_time)
    
    kb_time = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Bugun kechqurun"), KeyboardButton(text="Ertaga ertalab")],
        [KeyboardButton(text="1-2 soat ichida"), KeyboardButton(text="Hozir")]
    ], resize_keyboard=True, one_time_keyboard=True)
    
    await callback.message.delete()
    await callback.message.answer(
        f"🏁 Qayerga: <b>{place}</b>\n\n"
        f"⏰ <b>Taxminan qachon yo'lga chiqasiz?</b>",
        reply_markup=kb_time, parse_mode="HTML"
    )
    await callback.answer()

@router.message(ReturnTripStates.entering_time, F.text)
async def process_ret_time(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    ret_time = message.text.strip()
    data = await state.get_data()
    
    f_loc = data.get('ret_from', 'Toshkent')
    t_loc = data.get('ret_to', 'Chiroqchi')
    
    await set_driver_return_trip(user_id, f_loc, t_loc, ret_time)
    await state.clear()
    
    lang = await get_user_language(user_id)
    await message.answer(
        f"✅ <b>Qaytish yo'nalishi saqlandi!</b>\n━━━━━━━━━━━━━━\n"
        f"📍 <b>{f_loc} ➡️ {t_loc}</b>\n"
        f"⏰ <b>Vaqt:</b> {ret_time}\n\n"
        f"Ushbu yo'nalishda yangi buyurtmalar tushsa, birinchi navbatda sizga xabar beriladi! 🚀",
        reply_markup=await get_driver_menu(is_online=True, lang=lang),
        parse_mode="HTML"
    )
