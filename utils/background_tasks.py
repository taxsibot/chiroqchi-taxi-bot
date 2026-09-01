import asyncio
import logging
from datetime import datetime
from database.db import (
    get_upcoming_scheduled_orders, mark_order_notified, get_user, 
    get_old_pending_orders, update_order_status, get_setting, update_setting,
    get_charity_donors, clear_charity_donations, get_active_targeted_charities, get_groups_list
)
from aiogram import Bot

logger = logging.getLogger(__name__)

async def scheduled_orders_checker(bot: Bot):
    """
    Background task to check for upcoming scheduled orders and notify users.
    Runs every 5 minutes.
    """
    while True:
        logger.debug("Heartbeat: scheduled_orders_checker is alive")
        try:
            upcoming_orders = await get_upcoming_scheduled_orders()
            now = datetime.now()
            
            for order in upcoming_orders:
                # 0:id, 1:p_id, 2:d_id, 3:from, 4:to, 5:price, 6:p_cnt, 7:sched_time, 8:notif, 9:f_lat, 10:f_lon, 11:status, 12:ts
                order_id = order[0]
                p_id = order[1]
                d_id = order[2]
                scheduled_str = order[7] # 'DD.MM.YYYY HH:MM'
                status = order[11]
                
                if not scheduled_str:
                    continue
                    
                try:
                    scheduled_dt = datetime.strptime(scheduled_str, "%d.%m.%Y %H:%M")
                    diff = (scheduled_dt - now).total_seconds() / 60
                    
                    # Notify 30 minutes before
                    if 0 < diff <= 35:
                        # Notify Passenger
                        p_text = (
                            f"<b>🔔 ESLATMA!</b>\n\n"
                            f"Sizning buyurtmangizga oz vaqt qoldi.\n"
                            f"⏰ Vaqt: <b>{scheduled_str}</b>\n"
                            f"📍 Manzil: {order[3]} ➔ {order[4]}"
                        )
                        try:
                            await bot.send_message(p_id, p_text, parse_mode="HTML")
                        except Exception as e:
                            logger.warning(f"Could not notify passenger {p_id} for order #{order_id}: {e}")
                        
                        # Notify Driver (if accepted)
                        if d_id and status == 'accepted':
                            d_text = (
                                f"<b>🔔 ESLATMA (Haydovchi)!</b>\n\n"
                                f"Siz band qilgan buyurtmaga oz vaqt qoldi.\n"
                                f"⏰ Vaqt: <b>{scheduled_str}</b>\n"
                                f"👤 Yo'lovchi bilan bog'lanishni unutmang."
                            )
                            try:
                                await bot.send_message(d_id, d_text, parse_mode="HTML")
                            except Exception as e:
                                logger.warning(f"Could not notify driver {d_id} for order #{order_id}: {e}")
                        
                        # Mark as notified in DB
                        await mark_order_notified(order_id)
                        logger.info(f"Notification sent for scheduled order #{order_id}")
                        
                except Exception as e:
                    logger.error(f"Error parsing date {scheduled_str} for order #{order_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in scheduled_orders_checker task: {e}")
            
        await asyncio.sleep(300) # Check every 5 minutes

async def cancel_and_notify(bot: Bot, order_id: int, p_id: int):
    """Helper to cancel order and notify passenger in parallel"""
    try:
        await update_order_status(order_id, 'cancelled')
        try:
            await bot.send_message(p_id, "⚠️ Sizning buyurtmangiz uzoq vaqt qabul qilinmagani sababli tizim tomonidan bekor qilindi.")
        except Exception as e:
            if "bot was blocked" not in str(e).lower():
                logger.warning(f"Could not notify passenger {p_id} about cancellation of order #{order_id}: {e}")
        return True
    except Exception as e:
        logger.error(f"Failed to cancel order #{order_id}: {e}")
        return False

async def cleanup_old_orders(bot: Bot):
    """
    Background task to cancel pending orders older than 2 hours.
    Runs every hour.
    """
    while True:
        logger.debug("Heartbeat: cleanup_old_orders is alive")
        try:
            # Cancel orders older than 0.5 hours (30 minutes)
            old_orders = await get_old_pending_orders(0.5)
            
            if old_orders:
                tasks = [cancel_and_notify(bot, order_id, p_id) for order_id, p_id in old_orders]
                results = await asyncio.gather(*tasks)
                success_count = sum(1 for r in results if r)
                logger.info(f"Cleaned up {success_count} old orders.")
        except Exception as e:
            logger.error(f"Error in cleanup_old_orders task: {e}")
            
        await asyncio.sleep(600) # Check every 10 minutes

async def database_optimizer():
    """
    Background task to run VACUUM and ANALYZE on the database.
    Runs first time after 10 minutes, then every 24 hours.
    """
    from config import DB_PATH
    import aiosqlite
    
    # Wait 10 minutes after startup for the first optimization
    await asyncio.sleep(600)
    
    while True:
        logger.info("Starting database optimization (VACUUM/ANALYZE)...")
        try:
            # Must run outside of a transaction, so we use a dedicated connection with isolation_level=None
            async with aiosqlite.connect(DB_PATH, isolation_level=None) as vac_db:
                await vac_db.execute("VACUUM")
                await vac_db.execute("ANALYZE")
            logger.info("Database optimized successfully.")
        except Exception as e:
            logger.error(f"Error optimizing database: {e}")
            
        # Wait for 24 hours for the next cycle
        await asyncio.sleep(86400)

async def charity_cleanup_task(bot: Bot):
    """
    Background task to:
    1. Reset 'charity_p_total' (Monthly) on the 1st of each month.
    2. Clear one-off charity when its expiry date passes.
    """
    while True:
        try:
            now = datetime.now()
            
            # 1. Monthly Reset (Doimiy Ehson)
            # Check if today is the 1st of the month and we haven't reset yet today
            if now.day == 1:
                last_reset = await get_setting('charity_last_monthly_reset', '')
                current_month = now.strftime("%Y-%m")
                if last_reset != current_month:
                    await update_setting('charity_p_total', '0')
                    await update_setting('charity_last_monthly_reset', current_month)
                    logger.info(f"Monthly charity reset performed for {current_month}")

            # 2. One-off Charity Expiry (Maqsadli Ehson)
            expiry_str = await get_setting('charity_o_expiry', '') # Format: DD.MM.YYYY
            if expiry_str:
                try:
                    expiry_dt = datetime.strptime(expiry_str, "%d.%m.%Y")
                    # If expiry date has passed (yesterday or earlier)
                    if now.date() > expiry_dt.date():
                        # Get all donors for this one-off charity
                        donors = await get_charity_donors('o')
                        total_collected = await get_setting('charity_o_total', '0')
                        
                        # Send Thank You message
                        thank_you_text = (
                            f"<b>🙏 ALLOH ROZI BO'LSIN! (Rahmatnoma)</b>\n"
                            f"━━━━━━━━━━━━━━\n"
                            f"Siz ishtirok etgan maqsadli ehson yig'uvi muvaffaqiyatli yakunlandi.\n\n"
                            f"📊 <b>Jami to'plangan:</b> <b>{int(float(total_collected)):,} so'm</b>\n\n"
                            f"Siz kabi saxovatli insonlar sababli muhtojlarning mushkuli oson bo'ldi. "
                            f"Ehsoningizni Alloh dargohida qabul qilsin! ✨"
                        )
                        
                        for uid in donors:
                            try:
                                await bot.send_message(uid, thank_you_text, parse_mode="HTML")
                                await asyncio.sleep(0.05) # Flood limit protection
                            except: pass
                            
                        # Clear data
                        await update_setting('charity_o_total', '0')
                        await update_setting('charity_o_expiry', '')
                        await update_setting('charity_o_info', '')
                        await update_setting('charity_o_media_id', '')
                        await clear_charity_donations('o') # Clear donor list for 'o'
                        
                        logger.info(f"One-off charity expired, thank you messages sent to {len(donors)} users.")
                except Exception as e:
                    logger.error(f"Error parsing charity expiry date {expiry_str}: {e}")

        except Exception as e:
            logger.error(f"Error in charity_cleanup_task: {e}")
            
        # Check every 1 hour
        await asyncio.sleep(3600)

async def charity_daily_broadcast_task(bot: Bot):
    """
    Background task to broadcast active targeted charities to all groups every 24 hours.
    """
    while True:
        try:
            # Wait until a specific time (e.g., 10:00 AM) or just every 24h
            # For simplicity, let's run it every 24 hours
            active_charities = await get_active_targeted_charities()
            groups = await get_groups_list()
            bot_info = await bot.get_me()
            
            if active_charities and groups:
                for c in active_charities:
                    # cid, title, desc, target, current, expiry, media_id, m_type
                    cid, title, desc, target, current, expiry, media_id, m_type = c[:8]
                    
                    broadcast_text = (
                        f"<b>📢 KUNLIK ESLATMA: EHSON YIG'UVI</b>\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"✨ <b>{title}</b>\n\n"
                        f"📝 {desc}\n\n"
                        f"📊 To'plandi: <b>{int(current):,} / {int(target):,} so'm</b>\n"
                        f"📅 Muddat: <b>{expiry}</b> gacha\n\n"
                        f"👇 Yordam berish uchun botga o'ting:\n"
                        f"👉 @{bot_info.username}"
                    )
                    
                    for gid in groups:
                        try:
                            if media_id:
                                if m_type == 'video':
                                    await bot.send_video(gid, media_id, caption=broadcast_text, parse_mode="HTML")
                                else:
                                    await bot.send_photo(gid, media_id, caption=broadcast_text, parse_mode="HTML")
                            else:
                                await bot.send_message(gid, broadcast_text, parse_mode="HTML")
                            await asyncio.sleep(0.1) # Avoid flood
                        except: pass
                        
                logger.info(f"Daily charity broadcast sent to {len(groups)} groups.")

        except Exception as e:
            logger.error(f"Error in charity_daily_broadcast_task: {e}")
            
        # Run once every 24 hours
        await asyncio.sleep(86400)
