import sys
import os
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Auto-repair database package if running in container or missing directory
db_dir = os.path.join(BASE_DIR, "database")
if not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)
db_init = os.path.join(db_dir, "__init__.py")
if not os.path.exists(db_init):
    with open(db_init, "w", encoding="utf-8") as f:
        f.write("# database package\n")

# If db.py is in root instead of database/, mirror it into database/
root_db_py = os.path.join(BASE_DIR, "db.py")
target_db_py = os.path.join(db_dir, "db.py")
if os.path.exists(root_db_py) and not os.path.exists(target_db_py):
    shutil.copy(root_db_py, target_db_py)

import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ErrorEvent
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from config import BOT_TOKEN, USE_PROXY, PROXY_URL, ADMIN_ID
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic._internal._fields")

try:
    from database.db import init_db
except ModuleNotFoundError:
    import db as db_module
    init_db = db_module.init_db

from handlers import (
    registration, passenger, parcel, driver, admin, support, 
    common, profile, monitor, wallet, rating, inline, 
    chat, ai_handler, smart_order
)
from utils.set_bot_commands import set_commands
from utils.background_tasks import (
    scheduled_orders_checker, cleanup_old_orders, 
    database_optimizer, charity_cleanup_task, charity_daily_broadcast_task
)


# Configure logging for production (Rotating File Handler)
from logging.handlers import RotatingFileHandler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler("bot.log", maxBytes=5*1024*1024, backupCount=5, encoding="utf-8"), # 5MB limit per file
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def main():
    # Initialize database
    await init_db()
    
    # Session configuration (optimized for aiogram 3.x)
    session = None
    if USE_PROXY and PROXY_URL:
        session = AiohttpSession(proxy=PROXY_URL, timeout=30.0)
        logging.info(f"Using proxy: {PROXY_URL}")
    else:
        session = AiohttpSession(timeout=30.0)
    
    # ─── Render.com / Cloud Health Check Server (24/7 Uptime) ───────────────────
    import os
    from aiohttp import web
    port = int(os.environ.get("PORT", 8080))
    async def _health_handler(request):
        return web.Response(text="🚕 Chiroqchi Taxi Bot is running 24/7!", content_type="text/plain")
    
    async def _start_health_server():
        try:
            app = web.Application()
            app.router.add_get("/", _health_handler)
            app.router.add_get("/health", _health_handler)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            await site.start()
            logging.info(f"✅ Health Check Web Server started on port {port}")
        except Exception as e:
            logging.warning(f"Health server failed to start on port {port}: {e}")
    await _start_health_server()
    # ────────────────────────────────────────────────────────────────────────────
    
    # Initialize bot and dispatcher
    bot = Bot(
        token=BOT_TOKEN, 
        session=session, 
        default=DefaultBotProperties(parse_mode="HTML")
    )
    dp = Dispatcher()
    
    # Register Middlewares
    from utils.state_guard import StateGuardMiddleware
    from utils.group_tracker import GroupTrackerMiddleware
    from utils.throttling import ThrottlingMiddleware
    from utils.subscription_middleware import MandatorySubscriptionMiddleware
    from utils.autoreply_middleware import AutoReplyMiddleware
    from utils.language_middleware import LanguageMiddleware
    
    dp.message.outer_middleware(LanguageMiddleware())
    dp.callback_query.outer_middleware(LanguageMiddleware())
    dp.message.outer_middleware(ThrottlingMiddleware(limit=0.3)) # 0.3 second limit
    dp.message.outer_middleware(MandatorySubscriptionMiddleware())
    dp.callback_query.outer_middleware(MandatorySubscriptionMiddleware())
    dp.message.outer_middleware(StateGuardMiddleware())
    from utils.group_monitor_middleware import GroupMonitorMiddleware
    dp.message.outer_middleware(GroupMonitorMiddleware())
    dp.message.outer_middleware(GroupTrackerMiddleware())
    dp.message.outer_middleware(AutoReplyMiddleware())
    
    # Include routers
    dp.include_router(monitor.router)
    dp.include_router(registration.router)
    dp.include_router(passenger.router)
    dp.include_router(parcel.router)
    dp.include_router(driver.router)
    dp.include_router(admin.router)
    dp.include_router(support.router)
    dp.include_router(profile.router)
    dp.include_router(wallet.router)
    dp.include_router(rating.router)
    dp.include_router(inline.router)
    dp.include_router(chat.router)
    from utils.group_tracker import router as group_tracker_router
    dp.include_router(group_tracker_router)
    dp.include_router(smart_order.router)
    dp.include_router(ai_handler.router)
    dp.include_router(common.router)

    
    # Global Error Handler
    @dp.errors()
    async def global_error_handler(event: ErrorEvent):
        from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter, TelegramNetworkError, TelegramConflictError, TelegramServerError
        
        # Harmless errors to ignore (user actions or network blips, not bot bugs)
        if isinstance(event.exception, (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter, TelegramNetworkError, TelegramConflictError, TelegramServerError)):
            msg = str(event.exception).lower()
            # Ignore "message not modified", "bot blocked by user", "message to delete not found", etc.
            ignore_list = [
                "message is not modified", 
                "message to delete not found", 
                "query is too old", 
                "forbidden: bot was blocked", 
                "retry after",
                "message can't be deleted",
                "message to edit not found",
                "connection reset by peer",
                "timeout",
                "terminated by other getupdates request",
                "server closed"
            ]
            if any(x in msg for x in ignore_list):
                return
            
        logger.error(f"Global Error: {event.exception}", exc_info=True)
        
        try:
            # Only notify Admin for non-Telegram internal errors (actual code bugs)
            if not isinstance(event.exception, (TelegramBadRequest, TelegramForbiddenError)):
                user_id = "System"
                if event.update.message: user_id = event.update.message.from_user.id
                elif event.update.callback_query: user_id = event.update.callback_query.from_user.id
                
                await bot.send_message(
                    ADMIN_ID, 
                    f"🚨 <b>KRITIK XATOLIK</b>\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"❌ <b>Xato:</b> <code>{type(event.exception).__name__}</code>\n"
                    f"📝 <b>Tafsilot:</b> <code>{str(event.exception)[:500]}</code>\n"
                    f"👤 <b>Foydalanuvchi:</b> <code>{user_id}</code>"
                )
        except: 
            pass
    
    # Silence noisy loggers
    logging.getLogger("aiogram.event").setLevel(logging.WARNING) # Changed to WARNING to reduce "Update not handled" noise
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    async def on_startup(bot: Bot):
        # Start background tasks
        from utils.cache import cleanup_caches
        asyncio.create_task(scheduled_orders_checker(bot))
        asyncio.create_task(cleanup_old_orders(bot))
        asyncio.create_task(database_optimizer())
        asyncio.create_task(cleanup_caches())
        asyncio.create_task(charity_cleanup_task(bot))
        asyncio.create_task(charity_daily_broadcast_task(bot))
        
        # Initialize Main Admin in DB
        from database.db import add_admin
        await add_admin(ADMIN_ID, 'main')
        
        # Set bot commands
        try:
            await set_commands(bot)
        except Exception as e:
            logging.warning(f"Buyruqlarni o'rnatib bo'lmadi: {e}")
            
        logger.info("Bot muvaffaqiyatli ishga tushdi!")

    dp.startup.register(on_startup)
    
    # Start polling
    try:
        await dp.start_polling(
            bot, 
            allowed_updates=["message", "callback_query", "chat_member", "my_chat_member", "chat_join_request", "inline_query", "channel_post", "edited_channel_post", "edited_message"]
        )

    except Exception as e:
        logger.error(f"Bot startup/polling error: {e}")
    finally:
        from database.db import close_db
        await close_db()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
