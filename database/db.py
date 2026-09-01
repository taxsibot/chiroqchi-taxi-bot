import aiosqlite
import os
import logging
import asyncio
import time
from datetime import datetime, timedelta
from config import DB_PATH

logger = logging.getLogger(__name__)

SETTINGS_CACHE = {}
_db_connection = None

# New caches for high-frequency checks
# (These are imported from utils.cache in the functions below)

async def get_db():
    global _db_connection
    if _db_connection is None:
        _db_connection = await aiosqlite.connect(DB_PATH)
        await _db_connection.execute("PRAGMA journal_mode=WAL;")
        await _db_connection.execute("PRAGMA synchronous=NORMAL;")
        await _db_connection.execute("PRAGMA temp_store=MEMORY;")
        await _db_connection.execute("PRAGMA cache_size=-10000;")
        await _db_connection.execute("PRAGMA foreign_keys=ON;")
    return _db_connection

async def close_db():
    global _db_connection
    if _db_connection:
        await _db_connection.close()
        _db_connection = None

class DatabaseContext:
    """Context manager to reuse global connection without closing it."""
    async def __aenter__(self):
        return await get_db()
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

def db_session():
    return DatabaseContext()

async def load_settings_cache():
    global SETTINGS_CACHE
    async with db_session() as db:
        async with db.execute("SELECT key, value FROM settings") as cursor:
            rows = await cursor.fetchall()
            SETTINGS_CACHE = {row[0]: row[1] for row in rows}
    return SETTINGS_CACHE

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with db_session() as db:
        # Tables definitions
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_starters (
                user_id INTEGER PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                phone TEXT,
                secondary_phone TEXT,
                role TEXT, -- 'passenger', 'driver', 'admin'
                status TEXT DEFAULT 'active',
                balance REAL DEFAULT 0.0,
                referred_by INTEGER DEFAULT NULL,
                language TEXT DEFAULT 'uz',
                last_bonus_date TEXT,
                reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                description TEXT,
                type TEXT, -- 'in', 'out'
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS drivers (
                user_id INTEGER PRIMARY KEY,
                car_name TEXT,
                car_number TEXT,
                car_class TEXT DEFAULT 'Standard',
                rating REAL DEFAULT 5.0,
                total_rides INTEGER DEFAULT 0,
                is_online BOOLEAN DEFAULT 0,
                is_approved BOOLEAN DEFAULT 0,
                available_seats INTEGER DEFAULT 4,
                subscription_expiry TIMESTAMP,
                pax_quota INTEGER DEFAULT 0,
                parcel_quota INTEGER DEFAULT 0,
                active_route TEXT DEFAULT 'all',
                work_type TEXT DEFAULT 'both', -- 'taxi', 'parcel', 'both'
                priority_expiry TIMESTAMP DEFAULT NULL,
                car_photo TEXT,
                lat REAL DEFAULT NULL,
                lon REAL DEFAULT NULL,
                last_location_update TIMESTAMP,
                badge_fast INTEGER DEFAULT 0,
                badge_clean INTEGER DEFAULT 0,
                badge_polite INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS saved_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                address TEXT,
                usage_count INTEGER DEFAULT 1,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, address)
            )
        """)
        # Migrations
        try: await db.execute("ALTER TABLE users ADD COLUMN cashback_balance REAL DEFAULT 0.0")
        except Exception as e: logging.debug(f"Migration (cashback_balance) skipped: {e}")
        try: await db.execute("ALTER TABLE drivers ADD COLUMN work_type TEXT DEFAULT 'both'")
        except Exception as e: logging.debug(f"Migration (work_type) skipped: {e}")
        try: await db.execute("ALTER TABLE drivers ADD COLUMN car_photo TEXT")
        except Exception as e: logging.debug(f"Migration (car_photo) skipped: {e}")
        try: await db.execute("ALTER TABLE drivers ADD COLUMN lat REAL DEFAULT NULL")
        except Exception as e: logging.debug(f"Migration (lat) skipped: {e}")
        try: await db.execute("ALTER TABLE drivers ADD COLUMN lon REAL DEFAULT NULL")
        except Exception as e: logging.debug(f"Migration (lon) skipped: {e}")
        try: await db.execute("ALTER TABLE drivers ADD COLUMN last_location_update TIMESTAMP")
        except Exception as e: logging.debug(f"Migration (last_location_update) skipped: {e}")
        try: await db.execute("ALTER TABLE drivers ADD COLUMN badge_fast INTEGER DEFAULT 0")
        except Exception as e: logging.debug(f"Migration (badge_fast) skipped: {e}")
        try: await db.execute("ALTER TABLE drivers ADD COLUMN badge_clean INTEGER DEFAULT 0")
        except Exception as e: logging.debug(f"Migration (badge_clean) skipped: {e}")
        try: await db.execute("ALTER TABLE drivers ADD COLUMN badge_polite INTEGER DEFAULT 0")
        except Exception as e: logging.debug(f"Migration (badge_polite) skipped: {e}")
        
        try:
            await db.execute("ALTER TABLE bot_starters ADD COLUMN timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except Exception:
            try:
                # Some SQLite versions/builds don't allow DEFAULT CURRENT_TIMESTAMP in ALTER TABLE
                await db.execute("ALTER TABLE bot_starters ADD COLUMN timestamp TIMESTAMP")
                await db.execute("UPDATE bot_starters SET timestamp = CURRENT_TIMESTAMP WHERE timestamp IS NULL")
            except Exception as e:
                logging.debug(f"Migration (bot_starters.timestamp) skipped or failed: {e}")
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                passenger_id INTEGER,
                driver_id INTEGER DEFAULT NULL,
                from_location TEXT,
                to_location TEXT,
                price REAL,
                passenger_count INTEGER DEFAULT 1,
                scheduled_time TEXT DEFAULT NULL,
                notified INTEGER DEFAULT 0,
                from_lat REAL DEFAULT NULL,
                from_lon REAL DEFAULT NULL,
                status TEXT DEFAULT 'pending', -- 'pending', 'accepted', 'arrived', 'finished', 'cancelled'
                car_class TEXT DEFAULT 'Standard',
                order_type TEXT DEFAULT 'taxi', -- 'taxi', 'parcel'
                parcel_photo TEXT DEFAULT NULL,
                live_loc_msg_id INTEGER DEFAULT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (passenger_id) REFERENCES users(user_id),
                FOREIGN KEY (driver_id) REFERENCES users(user_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER UNIQUE,
                passenger_id INTEGER,
                driver_id INTEGER,
                stars INTEGER,
                comment TEXT DEFAULT NULL,
                badges TEXT DEFAULT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Migrations for ratings
        try: await db.execute("ALTER TABLE ratings ADD COLUMN badges TEXT")
        except Exception as e: logging.debug(f"Migration (ratings.badges) skipped: {e}")
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bids (
                bid_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                driver_id INTEGER,
                amount REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(order_id),
                FOREIGN KEY (driver_id) REFERENCES users(user_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE,
                invite_link TEXT,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                amount REAL,
                usage_limit INTEGER,
                used_count INTEGER DEFAULT 0,
                expiry_date TIMESTAMP DEFAULT NULL
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                subscription_guard INTEGER DEFAULT 0,
                is_order_channel INTEGER DEFAULT 1,
                is_parcel_channel INTEGER DEFAULT 1,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            await db.execute("UPDATE groups SET is_order_channel = 1, is_parcel_channel = 1 WHERE is_order_channel = 0 OR is_order_channel IS NULL")
        except Exception:
            pass


        await db.execute("""
            CREATE TABLE IF NOT EXISTS auto_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE,
                reply TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount REAL,
                details TEXT,
                status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                photo_id TEXT,
                status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS targeted_charities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                description TEXT,
                target_amount REAL DEFAULT 0,
                current_amount REAL DEFAULT 0,
                expiry_date TEXT, -- DD.MM.YYYY
                media_id TEXT,
                media_type TEXT DEFAULT 'photo',
                is_active INTEGER DEFAULT 1,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS charity_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                charity_id INTEGER,
                amount REAL,
                photo_id TEXT,
                status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (charity_id) REFERENCES targeted_charities(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS charity_donations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                charity_type TEXT, -- 'p' (permanent) or 'o' (one-off)
                charity_id INTEGER DEFAULT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                role TEXT DEFAULT 'assistant', -- 'main', 'assistant'
                permissions TEXT DEFAULT 'all', -- Comma separated: stats,users,drivers,orders...
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- 💺 HAMROH / POPUTCHIK REYSLARI ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rides (
                ride_id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id INTEGER,
                from_location TEXT,
                to_location TEXT,
                departure_time TEXT,
                total_seats INTEGER DEFAULT 4,
                available_seats INTEGER DEFAULT 4,
                price_per_seat REAL,
                car_model TEXT,
                car_number TEXT,
                notes TEXT,
                status TEXT DEFAULT 'active', -- 'active', 'completed', 'cancelled'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (driver_id) REFERENCES users(user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS ride_bookings (
                booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ride_id INTEGER,
                passenger_id INTEGER,
                seats_count INTEGER DEFAULT 1,
                status TEXT DEFAULT 'confirmed', -- 'confirmed', 'cancelled'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ride_id) REFERENCES rides(ride_id),
                FOREIGN KEY (passenger_id) REFERENCES users(user_id)
            )
        """)

        # --- 🔄 POPUTKA / QAYTISHGA YO'LOVCHI ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS return_trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id INTEGER,
                from_location TEXT,
                to_location TEXT,
                available_from_time TEXT,
                status TEXT DEFAULT 'active', -- 'active', 'completed', 'expired'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (driver_id) REFERENCES users(user_id)
            )
        """)

        # Indexes for Performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_passenger ON orders(passenger_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_driver ON orders(driver_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_referred ON users(referred_by)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_drivers_online ON drivers(is_online)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_drivers_approved ON drivers(is_approved)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_groups_order_channel ON groups(is_order_channel)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bids_order ON bids(order_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_rides_driver ON rides(driver_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_rides_status ON rides(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ride_bookings_ride ON ride_bookings(ride_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ride_bookings_passenger ON ride_bookings(passenger_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_return_trips_driver ON return_trips(driver_id)")
        
        # Default Settings
        default_settings = {
            'min_price': '5000',
            'max_price': '100000',
            'commission_rate': '10',
            'cashback_rate': '3',
            'min_driver_balance': '20000',
            'order_limit': '5',
            'ref_bonus': '500',
            'cancellation_penalty': '1000',
            'btn_app': '1',
            'btn_my_orders': '1',
            'btn_leaderboard': '1',
            'btn_add_group': '1',
            'btn_write_admin': '1',
            'btn_bonus': '1',
            'btn_promo': '1',
            'btn_wallet': '1',
            'btn_profile': '1',
            'btn_referral': '1',
            'btn_manual': '1',
            'btn_charity': '1',
            'btn_order_taxi': '1',
            'btn_order_parcel': '1',
            'btn_priority': '1',
            'btn_chat': '1',
            'btn_live_location': '1',
            'bot_maintenance': '0',
            'is_paid_plan': '0',
            'is_comm_enabled': '1',
            'trial_new_driver_enabled': '1',
            'trial_new_driver_type': 'days',
            'trial_new_driver_amount': '3',
            'leaderboard_enabled': '1',
            'leaderboard_prize_amount': '10000',
            'priority_delay': '10',
            'priority_price_daily': '5000',
            'group_broadcasting_enabled': '1',
            'commission_rate_taxi': '10',
            'commission_rate_parcel': '10',
            'tariff_daily_price': '10000',
            'tariff_monthly_price': '200000',
            'tariff_pax_unit_price': '5000',
            'tariff_parcel_unit_price': '3000',
            'tariff_pax_units': '10',
            'tariff_parcel_units': '10',
            'charity_card': "O'rnatilmagan",
            'charity_info': "Tez orada batafsil ma'lumot beriladi.",
            'charity_total': '0',
            'admin_card': "O'rnatilmagan",
            'manual_video_passenger': 'https://youtube.com',
            'manual_video_driver': 'https://youtube.com',
            'ai_support_enabled': '1',
            'admin_url': 'https://t.me/Admeral2002',
            'ocr_enabled': '1',
            'auto_dispatch_enabled': '1',
            'auto_dispatch_radius': '5',
            'comfort_price_extra': '5000',
            'business_price_extra': '10000'
        }
        for key, val in default_settings.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
        
        await db.commit()
        await load_settings_cache()

# --- Core Helpers ---

async def get_setting(key, default=None):
    return SETTINGS_CACHE.get(key, default)

def get_setting_sync(key, default=None):
    return SETTINGS_CACHE.get(key, default)

async def update_setting(key, value):
    global SETTINGS_CACHE
    async with db_session() as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()
        SETTINGS_CACHE[key] = str(value)
        logger.info(f"Setting updated and cached: {key}")

async def update_settings_bulk(settings_dict):
    global SETTINGS_CACHE
    async with db_session() as db:
        for key, value in settings_dict.items():
            await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            SETTINGS_CACHE[key] = str(value)
        await db.commit()
        logger.info(f"Bulk settings updated and cached: {list(settings_dict.keys())}")

# --- User Management ---

async def add_user(user_id, full_name, phone, role, secondary_phone=None, referred_by=None):
    async with db_session() as db:
        # Check if user exists to preserve referred_by if needed
        async with db.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            is_new = row is None
            existing_ref = row[0] if row else None
        
        final_ref = referred_by if referred_by else existing_ref
        
        await db.execute(
            "INSERT OR REPLACE INTO users (user_id, full_name, phone, secondary_phone, role, referred_by) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, full_name, phone, secondary_phone, role, final_ref)
        )
        await db.commit()
        return is_new

async def mark_user_started(user_id):
    from utils.cache import USER_STARTED_CACHE
    async with db_session() as db:
        await db.execute("INSERT OR IGNORE INTO bot_starters (user_id, timestamp) VALUES (?, CURRENT_TIMESTAMP)", (user_id,))
        await db.commit()
    USER_STARTED_CACHE[user_id] = (time.time(), True)

async def remove_user_started(user_id):
    from utils.cache import USER_STARTED_CACHE
    async with db_session() as db:
        await db.execute("DELETE FROM bot_starters WHERE user_id = ?", (user_id,))
        await db.commit()
    USER_STARTED_CACHE[user_id] = (time.time(), False)

async def has_user_started(user_id):
    from utils.cache import USER_STARTED_CACHE
    now = time.time()
    cached = USER_STARTED_CACHE.get(user_id)
    if cached and (now - cached[0]) < 300: # 5 min cache
        return cached[1]
        
    async with db_session() as db:
        sql = "SELECT 1 FROM bot_starters WHERE user_id = ? UNION SELECT 1 FROM users WHERE user_id = ?"
        async with db.execute(sql, (user_id, user_id)) as cursor:
            res = bool(await cursor.fetchone())
            USER_STARTED_CACHE[user_id] = (now, res)
            return res

async def get_user(user_id):
    async with db_session() as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def update_user_balance_conn(db, user_id, amount, description, trans_type='in'):
    """Atomic update using existing connection with negative balance protection"""
    # Use CASE to prevent negative balance if it's a deduction
    if amount < 0:
        sql = "UPDATE users SET balance = balance + ? WHERE user_id = ? AND balance + ? >= 0"
        cursor = await db.execute(sql, (amount, user_id, amount))
        if cursor.rowcount == 0:
            raise ValueError("Insufficient funds")
    else:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        
    await db.execute(
        "INSERT INTO transactions (user_id, amount, description, type) VALUES (?, ?, ?, ?)",
        (user_id, abs(amount), description, trans_type)
    )

async def add_withdrawal_request(req_id, user_id, amount, details):
    async with db_session() as db:
        await db.execute(
            "INSERT INTO withdrawals (id, user_id, amount, details, status) VALUES (?, ?, ?, ?, ?)",
            (req_id, user_id, amount, details, 'pending')
        )
        await db.commit()

async def get_withdrawal_request(req_id):
    async with db_session() as db:
        async with db.execute("SELECT * FROM withdrawals WHERE id = ?", (req_id,)) as cursor:
            return await cursor.fetchone()

async def update_withdrawal_status(req_id, status):
    async with db_session() as db:
        await db.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (status, req_id))
        await db.commit()

async def get_pending_withdrawals():
    async with db_session() as db:
        sql = """
            SELECT w.*, u.full_name 
            FROM withdrawals w 
            JOIN users u ON w.user_id = u.user_id 
            WHERE w.status = 'pending' 
            ORDER BY w.timestamp DESC
        """
        async with db.execute(sql) as cursor:
            return await cursor.fetchall()

async def update_user_balance(user_id, amount, description, trans_type='in'):
    async with db_session() as db:
        await update_user_balance_conn(db, user_id, amount, description, trans_type)
        await db.commit()

async def get_user_language(user_id):
    from utils.cache import LANG_CACHE, LANG_CACHE_TTL
    now = time.time()
    cached = LANG_CACHE.get(user_id)
    if cached and (now - cached[0]) < LANG_CACHE_TTL:
        return cached[1]
    async with db_session() as db:
        async with db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row and row[0] else 'uz'
            LANG_CACHE[user_id] = (now, lang)
            return lang

async def update_user_language(user_id, lang):
    from utils.cache import LANG_CACHE
    async with db_session() as db:
        await db.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
        await db.commit()
    # Invalidate cache
    LANG_CACHE[user_id] = (time.time(), lang)

async def get_user_status_counts():
    async with db_session() as db:
        async with db.execute("SELECT status, COUNT(*) FROM users GROUP BY status") as cursor:
            rows = await cursor.fetchall()
            stats = {'active': 0, 'blocked': 0}
            for status, count in rows:
                if status in stats:
                    stats[status] = count
            return stats

async def update_user_status(user_id, status):
    async with db_session() as db:
        await db.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))
        await db.commit()

# --- Driver Management ---

async def add_driver_details(user_id, car_name, car_number, is_approved=0, car_class='Standard', car_photo=None):
    async with db_session() as db:
        await db.execute(
            "INSERT OR REPLACE INTO drivers (user_id, car_name, car_number, is_approved, car_class, car_photo) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, car_name, car_number, is_approved, car_class, car_photo)
        )
        await db.commit()

async def get_driver(user_id):
    async with db_session() as db:
        async with db.execute("SELECT * FROM drivers WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def get_driver_by_car_number(car_number):
    async with db_session() as db:
        async with db.execute("SELECT * FROM drivers WHERE car_number = ?", (car_number,)) as cursor:
            return await cursor.fetchone()

async def set_driver_status(user_id, is_online: bool):
    async with db_session() as db:
        await db.execute("UPDATE drivers SET is_online = ? WHERE user_id = ?", (1 if is_online else 0, user_id))
        await db.commit()

async def get_online_drivers_with_route():
    async with db_session() as db:
        async with db.execute("SELECT user_id, active_route FROM drivers WHERE is_online = 1 AND is_approved = 1") as cursor:
            return await cursor.fetchall()

async def set_driver_route(user_id, route):
    async with db_session() as db:
        await db.execute("UPDATE drivers SET active_route = ? WHERE user_id = ?", (route, user_id))
        await db.commit()

async def update_driver_location(user_id, lat, lon):
    async with db_session() as db:
        await db.execute("UPDATE drivers SET lat = ?, lon = ?, last_location_update = CURRENT_TIMESTAMP WHERE user_id = ?", (lat, lon, user_id))
        await db.commit()

# --- Order Management ---

async def create_order(passenger_id, from_loc, to_loc, price, passenger_count=1, scheduled_time=None, from_lat=None, from_lon=None, car_class='Standard', order_type='taxi', parcel_photo=None):
    async with db_session() as db:
        cursor = await db.execute(
            "INSERT INTO orders (passenger_id, from_location, to_location, price, passenger_count, scheduled_time, from_lat, from_lon, car_class, order_type, parcel_photo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (passenger_id, from_loc, to_loc, price, passenger_count, scheduled_time, from_lat, from_lon, car_class, order_type, parcel_photo)
        )
        order_id = cursor.lastrowid
        await db.commit()
        return order_id

async def get_order(order_id):
    async with db_session() as db:
        async with db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)) as cursor:
            return await cursor.fetchone()

async def get_old_pending_orders(hours=2):
    async with db_session() as db:
        modifier = f"-{hours} hours"
        sql = "SELECT order_id, passenger_id FROM orders WHERE status = 'pending' AND timestamp < datetime('now', ?)"
        async with db.execute(sql, (modifier,)) as cursor:
            return await cursor.fetchall()

async def accept_order(order_id, driver_id):
    async with db_session() as db:
        # 1. Verification
        async with db.execute("SELECT status, passenger_count, price, order_type FROM orders WHERE order_id = ?", (order_id,)) as cursor:
            order = await cursor.fetchone()
            if not order or order[0] != 'pending': return False, "Already taken"
            p_count, price, o_type = order[1], order[2], order[3]

        async with db.execute("SELECT available_seats, subscription_expiry, pax_quota, parcel_quota FROM drivers WHERE user_id = ?", (driver_id,)) as cursor:
            driver = await cursor.fetchone()
            if not driver: return False, "Driver not found"
            seats, sub, p_quota, pc_quota = driver[0], driver[1], driver[2] or 0, driver[3] or 0
        
        if seats < p_count: return False, f"Not enough seats ({seats})"

        # 2. Plan Check
        is_paid_plan = (await get_setting('is_paid_plan', '0') == '1')
        is_comm_on = (await get_setting('is_comm_enabled', '1') == '1')
        take_commission = True
        
        if is_paid_plan:
            try:
                has_sub = sub and datetime.fromisoformat(str(sub)) > datetime.now()
            except (ValueError, TypeError):
                has_sub = False
            if not has_sub:
                if o_type == 'taxi' and p_quota > 0:
                    await db.execute("UPDATE drivers SET pax_quota = pax_quota - 1 WHERE user_id = ?", (driver_id,))
                    take_commission = False
                elif o_type == 'parcel' and pc_quota > 0:
                    await db.execute("UPDATE drivers SET parcel_quota = parcel_quota - 1 WHERE user_id = ?", (driver_id,))
                    take_commission = False
                else:
                    return False, "No active plan/quota"
            else:
                take_commission = False
        
        # Override commission if globally disabled in settings
        if take_commission and not is_comm_on:
            take_commission = False
        
        if take_commission:
            # Check balance (using setting)
            min_bal = float(await get_setting('min_driver_balance', '20000'))
            async with db.execute("SELECT balance FROM users WHERE user_id = ?", (driver_id,)) as cursor:
                row = await cursor.fetchone()
                if not row: return False, "Driver balance info not found"
                bal = row[0]
                if bal < min_bal: return False, f"Low balance: {bal:,} sum"
            
            if o_type == 'parcel':
                comm_rate = float(await get_setting('commission_rate_parcel', '10'))
            else:
                comm_rate = float(await get_setting('commission_rate_taxi', '10'))
                
            commission = price * (comm_rate / 100)
            await update_user_balance_conn(db, driver_id, -commission, f"Komissiya ({'Pochta' if o_type == 'parcel' else 'Taksi'})", 'out')

        # 3. Finalize - ATOMIC CHECK to prevent Race Conditions
        cursor = await db.execute("UPDATE orders SET driver_id = ?, status = 'accepted' WHERE order_id = ? AND status = 'pending'", (driver_id, order_id))
        if cursor.rowcount == 0:
            # Someone else took the order exactly at the same millisecond!
            await db.rollback()
            return False, "Already taken"
            
        await db.execute("UPDATE drivers SET available_seats = available_seats - ? WHERE user_id = ?", (p_count, driver_id))
        await db.commit()
        return True, "Success"

async def update_order_status(order_id, new_status):
    async with db_session() as db:
        async with db.execute("SELECT passenger_id, driver_id, passenger_count, status, price FROM orders WHERE order_id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            if not row: return False
            p_id, d_id, p_count, old_status, price = row

        if new_status == old_status:
            return True

        # ATOMIC CHECK: Ensure status hasn't changed since we read it
        cursor = await db.execute("UPDATE orders SET status = ? WHERE order_id = ? AND status = ?", (new_status, order_id, old_status))
        if cursor.rowcount == 0:
            await db.rollback()
            return False

        if new_status == 'finished':
            # Award cashback to passenger
            cashback_rate = float(await get_setting('cashback_rate', '5')) # Default 5%
            cashback_amount = (price * cashback_rate) / 100
            if cashback_amount > 0:
                await db.execute("UPDATE users SET cashback_balance = cashback_balance + ? WHERE user_id = ?", (cashback_amount, p_id))
                await db.execute("INSERT INTO transactions (user_id, amount, description, type) VALUES (?, ?, ?, ?)", 
                                 (p_id, cashback_amount, f"Keshbek (Buyurtma #{order_id})", 'in'))

        if new_status in ['finished', 'cancelled'] and old_status not in ['finished', 'cancelled']:
            if d_id:
                await db.execute("UPDATE drivers SET available_seats = available_seats + ? WHERE user_id = ?", (p_count, d_id))
                if new_status == 'cancelled':
                    # Refund commission if it was taken
                    async with db.execute("SELECT order_type FROM orders WHERE order_id = ?", (order_id,)) as cursor_type:
                        row_type = await cursor_type.fetchone()
                        o_type = row_type[0] if row_type else 'taxi'
                    
                    if o_type == 'parcel':
                        comm_rate = float(await get_setting('commission_rate_parcel', '10'))
                    else:
                        comm_rate = float(await get_setting('commission_rate_taxi', '10'))
                        
                    refund = price * (comm_rate / 100)
                    await update_user_balance_conn(db, d_id, refund, "Komissiya qaytarildi (Buyurtma)", 'in')
                
                if new_status == 'finished':
                    # 1. Increment total rides
                    await db.execute("UPDATE drivers SET total_rides = total_rides + 1 WHERE user_id = ?", (d_id,))
                    # 2. Referral
                    await handle_referral_bonuses(db, p_id, d_id)

        await db.commit()
        return True

async def handle_referral_bonuses(db, p_id, d_id):
    """Bonus for inviters on first ride completion"""
    bonus = int(await get_setting('ref_bonus', '500'))
    
    # Passenger inviter
    async with db.execute("SELECT COUNT(*) FROM orders WHERE passenger_id = ? AND status = 'finished'", (p_id,)) as c:
        if (await c.fetchone())[0] == 1:
            async with db.execute("SELECT referred_by FROM users WHERE user_id = ?", (p_id,)) as r:
                inviter = await r.fetchone()
                if inviter and inviter[0]:
                    await update_user_balance_conn(db, inviter[0], bonus, f"Referral: User {p_id} first ride", 'in')

    # Driver inviter
    async with db.execute("SELECT COUNT(*) FROM orders WHERE driver_id = ? AND status = 'finished'", (d_id,)) as c:
        if (await c.fetchone())[0] == 1:
            async with db.execute("SELECT referred_by FROM users WHERE user_id = ?", (d_id,)) as r:
                inviter = await r.fetchone()
                if inviter and inviter[0]:
                    await update_user_balance_conn(db, inviter[0], bonus, f"Referral: Driver {d_id} first ride", 'in')

# --- Promo & Bonus ---

async def check_claim_daily_bonus(user_id, amount=200):
    today = datetime.now().strftime("%Y-%m-%d")
    async with db_session() as db:
        async with db.execute("SELECT last_bonus_date FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] == today: return 0, "already_claimed"
            
            await update_user_balance_conn(db, user_id, amount, "Daily Bonus", 'in')
            await db.execute("UPDATE users SET last_bonus_date = ? WHERE user_id = ?", (today, user_id))
            await db.commit()
            return amount, "success"



async def validate_and_use_promocode(user_id, code):
    async with db_session() as db:
        async with db.execute("SELECT amount, usage_limit, used_count FROM promocodes WHERE code = ?", (code.upper(),)) as cursor:
            row = await cursor.fetchone()
            if not row: return 0, "not_found"
            amount, limit, used = row
            if used >= limit: return 0, "limit_reached"
            
            await update_user_balance_conn(db, user_id, amount, f"Promo: {code}", 'in')
            await db.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?", (code.upper(),))
            await db.commit()
            return amount, "success"

# --- Admin Helpers ---

async def get_detailed_stats(period='daily'):
    async with db_session() as db:
        if period == 'weekly':
            f = "date(timestamp) >= date('now', '-7 days')"
            uf = "date(reg_date) >= date('now', '-7 days')"
        elif period == 'monthly':
            f = "strftime('%Y-%m', timestamp) = strftime('%Y-%m', 'now')"
            uf = "strftime('%Y-%m', reg_date) = strftime('%Y-%m', 'now')"
        else:
            f = "date(timestamp) = date('now')"
            uf = "date(reg_date) = date('now')"
            
        async with db.execute(f"SELECT COUNT(*) FROM users WHERE {uf}") as c: 
            row = await c.fetchone()
            new_u = row[0] if row else 0
        async with db.execute(f"SELECT COUNT(*) FROM orders WHERE status = 'finished' AND {f}") as c: 
            row = await c.fetchone()
            fin_o = row[0] if row else 0
        async with db.execute(f"SELECT COUNT(*) FROM orders WHERE status = 'cancelled' AND {f}") as c: 
            row = await c.fetchone()
            can_o = row[0] if row else 0
        async with db.execute(f"SELECT SUM(price) FROM orders WHERE status = 'finished' AND {f}") as c: 
            row = await c.fetchone()
            rev = row[0] if row and row[0] else 0
        async with db.execute(f"SELECT SUM(amount) FROM transactions WHERE type = 'out' AND description LIKE '%komissiya%' AND {f}") as c: 
            row = await c.fetchone()
            prof = row[0] if row and row[0] else 0
        
        # New: Count groups and channels
        async with db.execute("SELECT COUNT(*) FROM groups") as c: gr_cnt = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM channels WHERE is_active = 1") as c: ch_cnt = (await c.fetchone())[0]
        
        # New: Withdrawal stats
        async with db.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'") as c: w_pending = (await c.fetchone())[0]
        async with db.execute("SELECT SUM(amount) FROM withdrawals WHERE status = 'approved' AND " + f) as c: w_total = (await c.fetchone())[0] or 0
        # Total unique subscribers (registered + started)
        async with db.execute("SELECT COUNT(user_id) FROM (SELECT user_id FROM users UNION SELECT user_id FROM bot_starters)") as c:
            row = await c.fetchone()
            total_u = row[0] if row else 0
        
    return {
        "revenue": rev,
        "profit": abs(prof),
        "finished": fin_o,
        "cancelled": can_o,
        "new_users": new_u,
        "total_users": total_u,
        "groups_count": gr_cnt,
        "channels_count": ch_cnt,
        "withdraw_pending": w_pending,
        "withdraw_total": w_total
    }

async def add_targeted_charity(title, desc, target, expiry, media_id=None, media_type='photo'):
    async with db_session() as db:
        cursor = await db.execute(
            "INSERT INTO targeted_charities (title, description, target_amount, expiry_date, media_id, media_type) VALUES (?, ?, ?, ?, ?, ?)",
            (title, desc, target, expiry, media_id, media_type)
        )
        cid = cursor.lastrowid
        await db.commit()
        return cid

async def get_active_targeted_charities():
    async with db_session() as db:
        async with db.execute("SELECT * FROM targeted_charities WHERE is_active = 1") as cursor:
            return await cursor.fetchall()

async def get_targeted_charity(cid):
    async with db_session() as db:
        async with db.execute("SELECT * FROM targeted_charities WHERE id = ?", (cid,)) as cursor:
            return await cursor.fetchone()

async def update_charity_amount(cid, amount):
    async with db_session() as db:
        await db.execute("UPDATE targeted_charities SET current_amount = current_amount + ? WHERE id = ?", (amount, cid))
        await db.commit()

async def add_charity_receipt(user_id, charity_id, amount, photo_id):
    async with db_session() as db:
        cursor = await db.execute(
            "INSERT INTO charity_receipts (user_id, charity_id, amount, photo_id) VALUES (?, ?, ?, ?)",
            (user_id, charity_id, amount, photo_id)
        )
        rid = cursor.lastrowid
        await db.commit()
        return rid

async def add_charity_donation(user_id, amount, charity_type, targeted_charity_id=None):
    async with db_session() as db:
        await db.execute(
            "INSERT INTO charity_donations (user_id, amount, charity_type, targeted_charity_id) VALUES (?, ?, ?, ?)",
            (user_id, amount, charity_type, targeted_charity_id)
        )
        await db.commit()

async def get_charity_donors(charity_type=None, targeted_charity_id=None):
    async with db_session() as db:
        if targeted_charity_id:
            async with db.execute("SELECT DISTINCT user_id FROM charity_donations WHERE targeted_charity_id = ?", (targeted_charity_id,)) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
        elif charity_type:
            async with db.execute("SELECT DISTINCT user_id FROM charity_donations WHERE charity_type = ?", (charity_type,)) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
        else:
            async with db.execute("SELECT DISTINCT user_id FROM charity_donations") as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

async def clear_charity_donations(charity_type=None, targeted_charity_id=None):
    async with db_session() as db:
        if targeted_charity_id:
            await db.execute("DELETE FROM charity_donations WHERE targeted_charity_id = ?", (targeted_charity_id,))
        elif charity_type:
            await db.execute("DELETE FROM charity_donations WHERE charity_type = ?", (charity_type,))
        else:
            await db.execute("DELETE FROM charity_donations")
        await db.commit()

async def get_users_list():
    async with db_session() as db:
        async with db.execute("SELECT user_id FROM bot_starters") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def get_groups_list():
    async with db_session() as db:
        async with db.execute("SELECT chat_id FROM groups") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def add_admin(user_id, role='assistant', permissions='all'):
    async with db_session() as db:
        await db.execute("INSERT OR REPLACE INTO admins (user_id, role, permissions) VALUES (?, ?, ?)", (user_id, role, permissions))
        await db.commit()

async def get_admin(user_id):
    async with db_session() as db:
        async with db.execute("SELECT * FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def remove_admin(user_id):
    async with db_session() as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_all_admins():
    async with db_session() as db:
        async with db.execute("SELECT * FROM admins") as cursor:
            return await cursor.fetchall()

async def is_admin_db(user_id):
    async with db_session() as db:
        async with db.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone() is not None

async def search_users(q):
    async with db_session() as db:
        val = f"%{q}%"
        async with db.execute("SELECT user_id, full_name, phone, role, status FROM users WHERE user_id LIKE ? OR phone LIKE ? OR full_name LIKE ?", (val, val, val)) as c:
            return await c.fetchall()



# --- Driver Subscription Extras ---

async def extend_driver_subscription(user_id, days):
    async with db_session() as db:
        async with db.execute("SELECT subscription_expiry FROM drivers WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            cur = datetime.fromisoformat(str(row[0])) if row and row[0] else datetime.now()
            start = cur if cur > datetime.now() else datetime.now()
            new = (start + timedelta(days=days)).isoformat()
            await db.execute("UPDATE drivers SET subscription_expiry = ? WHERE user_id = ?", (new, user_id))
            await db.commit()
            return new

async def add_driver_quota(user_id, pax=0, pc=0):
    async with db_session() as db:
        await db.execute("UPDATE drivers SET pax_quota = pax_quota + ?, parcel_quota = parcel_quota + ? WHERE user_id = ?", (pax, pc, user_id))
        await db.commit()

async def update_order_price(order_id, price):
    async with db_session() as db:
        await db.execute("UPDATE orders SET price = ? WHERE order_id = ?", (price, order_id))
        await db.commit()

async def get_passenger_id_by_order_id(order_id):
    async with db_session() as db:
        async with db.execute("SELECT passenger_id FROM orders WHERE order_id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

CHANNELS_LIST_CACHE = None
CHANNELS_LIST_CACHE_TIME = 0

async def get_active_channels():
    global CHANNELS_LIST_CACHE, CHANNELS_LIST_CACHE_TIME
    now = time.time()
    
    if CHANNELS_LIST_CACHE is not None and (now - CHANNELS_LIST_CACHE_TIME) < 300:
        return CHANNELS_LIST_CACHE
        
    async with db_session() as db:
        async with db.execute("SELECT channel_id, invite_link FROM channels WHERE is_active = 1") as cursor:
            CHANNELS_LIST_CACHE = await cursor.fetchall()
            CHANNELS_LIST_CACHE_TIME = now
            return CHANNELS_LIST_CACHE

async def add_channel(channel_id, invite_link):
    global CHANNELS_LIST_CACHE
    async with db_session() as db:
        await db.execute("INSERT INTO channels (channel_id, invite_link) VALUES (?, ?)", (channel_id, invite_link))
        await db.commit()
        CHANNELS_LIST_CACHE = None

async def remove_channel(channel_id):
    global CHANNELS_LIST_CACHE
    async with db_session() as db:
        await db.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
        await db.commit()
        CHANNELS_LIST_CACHE = None

async def clear_all_channels():
    global CHANNELS_LIST_CACHE
    async with db_session() as db:
        await db.execute("DELETE FROM channels")
        await db.commit()
        CHANNELS_LIST_CACHE = None



async def get_unapproved_drivers():
    async with db_session() as db:
        sql = "SELECT u.user_id, u.full_name, u.phone, d.car_name, d.car_number FROM users u JOIN drivers d ON u.user_id = d.user_id WHERE d.is_approved = 0"
        async with db.execute(sql) as cursor: return await cursor.fetchall()

async def approve_driver(user_id):
    async with db_session() as db:
        await db.execute("UPDATE drivers SET is_approved = 1 WHERE user_id = ?", (user_id,))
        
        # Apply Trial if enabled
        is_trial = (await get_setting('trial_new_driver_enabled', '0') == '1')
        if is_trial:
            trial_type = await get_setting('trial_new_driver_type', 'days')
            try:
                amount = int(await get_setting('trial_new_driver_amount', '3'))
            except:
                amount = 3
                
            if trial_type == 'days':
                # Extend subscription using existing helper
                async with db.execute("SELECT subscription_expiry FROM drivers WHERE user_id = ?", (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    cur = datetime.fromisoformat(str(row[0])) if row and row[0] else datetime.now()
                    start = cur if cur > datetime.now() else datetime.now()
                    new_expiry = (start + timedelta(days=amount)).isoformat()
                    await db.execute("UPDATE drivers SET subscription_expiry = ? WHERE user_id = ?", (new_expiry, user_id))
            else:
                # Add quota for both pax and parcel
                await db.execute("UPDATE drivers SET pax_quota = pax_quota + ?, parcel_quota = parcel_quota + ? WHERE user_id = ?", (amount, amount, user_id))
        
        await db.commit()

async def get_passenger_active_orders(p_id):
    async with db_session() as db:
        # Show 'accepted' and 'arrived' orders (taken by drivers)
        sql = """
            SELECT * FROM orders 
            WHERE passenger_id = ? 
            AND status IN ('accepted', 'arrived') 
            AND timestamp > datetime('now', '-24 hours')
            ORDER BY timestamp DESC
        """
        async with db.execute(sql, (p_id,)) as cursor: return await cursor.fetchall()

async def get_passenger_pending_orders(p_id):
    async with db_session() as db:
        # Show 'pending' orders (not yet taken by drivers)
        sql = """
            SELECT * FROM orders 
            WHERE passenger_id = ? 
            AND status = 'pending'
            AND timestamp > datetime('now', '-24 hours')
            ORDER BY timestamp DESC
        """
        async with db.execute(sql, (p_id,)) as cursor: return await cursor.fetchall()

async def get_driver_active_orders(d_id):
    async with db_session() as db:
        # Drivers only see orders they are currently serving
        sql = """
            SELECT * FROM orders 
            WHERE driver_id = ? 
            AND status IN ('accepted', 'arrived') 
            AND timestamp > datetime('now', '-24 hours')
            ORDER BY timestamp DESC
        """
        async with db.execute(sql, (d_id,)) as cursor: return await cursor.fetchall()

async def get_referral_stats(user_id):
    async with db_session() as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)) as c:
            return (await c.fetchone())[0]

async def get_referral_list(user_id):
    async with db_session() as db:
        async with db.execute("SELECT user_id, full_name, role, reg_date FROM users WHERE referred_by = ? ORDER BY reg_date DESC", (user_id,)) as c:
            return await c.fetchall()

async def get_driver_earnings_stats(d_id):
    async with db_session() as db:
        # Earnings today
        async with db.execute("SELECT SUM(price) FROM orders WHERE driver_id = ? AND status = 'finished' AND date(timestamp) = date('now')", (d_id,)) as c:
            today = (await c.fetchone())[0] or 0
        # Total earnings
        async with db.execute("SELECT SUM(price) FROM orders WHERE driver_id = ? AND status = 'finished'", (d_id,)) as c:
            total = (await c.fetchone())[0] or 0
        # Total commission paid (negative amounts in transactions)
        async with db.execute("SELECT SUM(abs(amount)) FROM transactions WHERE user_id = ? AND type = 'out' AND description LIKE 'Commission%'", (d_id,)) as c:
            commission = (await c.fetchone())[0] or 0
            
        return {"today": today, "total": total, "commission": commission}

async def get_driver_feedback(d_id, limit=5):
    async with db_session() as db:
        sql = "SELECT stars, comment, timestamp FROM ratings WHERE driver_id = ? ORDER BY timestamp DESC LIMIT ?"
        async with db.execute(sql, (d_id, limit)) as cursor: return await cursor.fetchall()

async def get_all_orders(limit=50):
    async with db_session() as db:
        async with db.execute("SELECT * FROM orders ORDER BY timestamp DESC LIMIT ?", (limit,)) as cursor:
            return await cursor.fetchall()


async def delete_user(user_id):
    async with db_session() as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM drivers WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM bot_starters WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM orders WHERE passenger_id = ? OR driver_id = ?", (user_id, user_id))
        await db.execute("DELETE FROM ratings WHERE passenger_id = ? OR driver_id = ?", (user_id, user_id))
        await db.execute("DELETE FROM withdrawals WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM bids WHERE driver_id = ?", (user_id,))
        await db.commit()

async def delete_blocked_users():
    async with db_session() as db:
        # First, find how many are blocked
        async with db.execute("SELECT COUNT(*) FROM users WHERE status = 'blocked'") as c:
            count = (await c.fetchone())[0]
            
        if count > 0:
            # Delete from related tables where user is blocked
            await db.execute("DELETE FROM drivers WHERE user_id IN (SELECT user_id FROM users WHERE status = 'blocked')")
            await db.execute("DELETE FROM bot_starters WHERE user_id IN (SELECT user_id FROM users WHERE status = 'blocked')")
            await db.execute("DELETE FROM transactions WHERE user_id IN (SELECT user_id FROM users WHERE status = 'blocked')")
            await db.execute("DELETE FROM orders WHERE passenger_id IN (SELECT user_id FROM users WHERE status = 'blocked') OR driver_id IN (SELECT user_id FROM users WHERE status = 'blocked')")
            await db.execute("DELETE FROM ratings WHERE passenger_id IN (SELECT user_id FROM users WHERE status = 'blocked') OR driver_id IN (SELECT user_id FROM users WHERE status = 'blocked')")
            await db.execute("DELETE FROM withdrawals WHERE user_id IN (SELECT user_id FROM users WHERE status = 'blocked')")
            await db.execute("DELETE FROM bids WHERE driver_id IN (SELECT user_id FROM users WHERE status = 'blocked')")
            # Finally delete from users table
            await db.execute("DELETE FROM users WHERE status = 'blocked'")
            await db.commit()
            
        return count

async def get_online_driver_ids():
    async with db_session() as db:
        async with db.execute("SELECT user_id FROM drivers WHERE is_online = 1 AND is_approved = 1") as c:
            return [r[0] for r in await c.fetchall()]

# --- Group Tracking ---

async def get_user_orders_history(user_id, role='passenger', limit=10):
    async with db_session() as db:
        if role == 'passenger':
            sql = "SELECT * FROM orders WHERE passenger_id = ? ORDER BY timestamp DESC LIMIT ?"
        else:
            sql = "SELECT * FROM orders WHERE driver_id = ? ORDER BY timestamp DESC LIMIT ?"
        async with db.execute(sql, (user_id, limit)) as cursor:
            return await cursor.fetchall()

async def get_user_full_order_history(user_id, role='passenger'):
    async with db_session() as db:
        if role == 'passenger':
            sql = "SELECT * FROM orders WHERE passenger_id = ? ORDER BY timestamp DESC"
        else:
            sql = "SELECT * FROM orders WHERE driver_id = ? ORDER BY timestamp DESC"
        async with db.execute(sql, (user_id,)) as cursor:
            return await cursor.fetchall()

async def add_group(chat_id, title):
    async with db_session() as db:
        await db.execute("""
            INSERT INTO groups (chat_id, title, is_order_channel, is_parcel_channel) 
            VALUES (?, ?, 1, 1) 
            ON CONFLICT(chat_id) DO UPDATE SET 
                title = excluded.title,
                is_order_channel = 1,
                is_parcel_channel = 1
        """, (chat_id, title))
        await db.commit()

async def delete_group(chat_id):
    async with db_session() as db:
        await db.execute("DELETE FROM groups WHERE chat_id = ?", (chat_id,))
        await db.commit()

async def clear_all_groups():
    async with db_session() as db:
        await db.execute("DELETE FROM groups")
        await db.commit()

async def get_all_groups():
    async with db_session() as db:
        async with db.execute("SELECT * FROM groups") as cursor:
            return await cursor.fetchall()

async def toggle_group_guard(chat_id, status: int = None):
    from utils.cache import GROUP_GUARD_CACHE
    async with db_session() as db:
        if status is None:
            async with db.execute("SELECT subscription_guard FROM groups WHERE chat_id = ?", (chat_id,)) as cursor:
                row = await cursor.fetchone()
                current = row[0] if row else 0
                status = 0 if current else 1
        await db.execute("INSERT INTO groups (chat_id, subscription_guard) VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET subscription_guard = ?", (chat_id, status, status))
        await db.commit()
        GROUP_GUARD_CACHE[chat_id] = (time.time(), bool(status))
        return bool(status)

async def is_group_guarded(chat_id):
    from utils.cache import GROUP_GUARD_CACHE
    now = time.time()
    cached = GROUP_GUARD_CACHE.get(chat_id)
    if cached and (now - cached[0]) < 600: # 10 min cache
        return cached[1]
        
    async with db_session() as db:
        async with db.execute("SELECT subscription_guard FROM groups WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            res = bool(row[0]) if row else False
            GROUP_GUARD_CACHE[chat_id] = (now, res)
            return res

async def get_order_channels(order_type='taxi'):
    async with db_session() as db:
        col = "is_parcel_channel" if order_type == 'parcel' else "is_order_channel"
        async with db.execute(f"SELECT chat_id FROM groups WHERE {col} = 1") as cursor:
            res = [row[0] for row in await cursor.fetchall()]
            if res:
                return res
        # Fallback: agar birorta ham guruh maxsus belgilanmagan bo'lsa, barcha guruhlarga yuborilsin
        async with db.execute("SELECT chat_id FROM groups") as cursor:
            return [row[0] for row in await cursor.fetchall()]


async def toggle_group_order_channel(chat_id, status: int = None):
    async with db_session() as db:
        if status is None:
            async with db.execute("SELECT is_order_channel FROM groups WHERE chat_id = ?", (chat_id,)) as cursor:
                row = await cursor.fetchone()
                current = row[0] if row else 0
                status = 0 if current else 1
        await db.execute("UPDATE groups SET is_order_channel = ? WHERE chat_id = ?", (status, chat_id))
        await db.commit()
        return bool(status)

async def toggle_group_parcel_channel(chat_id, status: int = None):
    async with db_session() as db:
        if status is None:
            async with db.execute("SELECT is_parcel_channel FROM groups WHERE chat_id = ?", (chat_id,)) as cursor:
                row = await cursor.fetchone()
                current = row[0] if row else 0
                status = 0 if current else 1
        await db.execute("UPDATE groups SET is_parcel_channel = ? WHERE chat_id = ?", (status, chat_id))
        await db.commit()
        return bool(status)

async def get_active_order_peer(user_id):
    """Returns the peer_id (passenger or driver) of the user's active order"""
    async with db_session() as db:
        # Check as passenger
        async with db.execute("SELECT driver_id FROM orders WHERE passenger_id = ? AND status IN ('accepted', 'arrived')", (user_id,)) as c:
            row = await c.fetchone()
            if row and row[0]: return row[0]
            
        # Check as driver
        async with db.execute("SELECT passenger_id FROM orders WHERE driver_id = ? AND status IN ('accepted', 'arrived')", (user_id,)) as c:
            row = await c.fetchone()
            if row and row[0]: return row[0]
            
    return None


async def reset_all_ratings_db():
    """Resets all driver ratings and clears history."""
    async with db_session() as db:
        # 1. Clear rating history
        await db.execute("DELETE FROM ratings")
        # 2. Reset scores in drivers table
        await db.execute("UPDATE drivers SET rating = 0.0, total_rides = 0")
        await db.commit()

# --- Additional Helpers ---

async def get_user_info(user_id):
    async with db_session() as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def get_driver_available_seats(d_id):
    async with db_session() as db:
        async with db.execute("SELECT available_seats FROM drivers WHERE user_id = ?", (d_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def add_bid(order_id, d_id, amount):
    async with db_session() as db:
        await db.execute("INSERT INTO bids (order_id, driver_id, amount) VALUES (?, ?, ?)", (order_id, d_id, amount))
        await db.commit()

async def get_logs(limit=100):
    async with db_session() as db:
        async with db.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,)) as cursor:
            return await cursor.fetchall()

async def get_top_drivers(limit=10):
    async with db_session() as db:
        sql = "SELECT u.full_name, d.car_name, d.rating, d.total_rides FROM users u JOIN drivers d ON u.user_id = d.user_id ORDER BY d.rating DESC, d.total_rides DESC LIMIT ?"
        async with db.execute(sql, (limit,)) as cursor: return await cursor.fetchall()

async def get_drivers_by_status(is_online: bool):
    async with db_session() as db:
        sql = """
            SELECT u.user_id, u.full_name, u.phone, d.car_name, d.car_number, d.rating, d.total_rides 
            FROM users u 
            JOIN drivers d ON u.user_id = d.user_id 
            WHERE d.is_online = ? AND d.is_approved = 1
        """
        async with db.execute(sql, (1 if is_online else 0,)) as cursor:
            return await cursor.fetchall()



async def get_driver_order_stats(d_id):
    async with db_session() as db:
        async with db.execute("SELECT COUNT(*) FROM orders WHERE driver_id = ? AND status = 'finished'", (d_id,)) as c:
            finished = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM orders WHERE driver_id = ? AND status = 'cancelled'", (d_id,)) as c:
            cancelled = (await c.fetchone())[0]
        return {"finished": finished, "cancelled": cancelled}

async def get_orders_by_status(status):
    async with db_session() as db:
        async with db.execute("SELECT * FROM orders WHERE status = ? ORDER BY timestamp DESC", (status,)) as cursor:
            return await cursor.fetchall()

async def get_orders_by_date(date_str):
    async with db_session() as db:
        async with db.execute("SELECT * FROM orders WHERE date(timestamp) = ? ORDER BY timestamp DESC", (date_str,)) as cursor:
            return await cursor.fetchall()

async def get_all_starters_with_dates():
    """Returns a list of (user_id, timestamp) for all who started the bot."""
    async with db_session() as db:
        sql = """
            SELECT user_id, reg_date as timestamp FROM users
            UNION
            SELECT user_id, timestamp FROM bot_starters
            ORDER BY timestamp DESC
        """
        async with db.execute(sql) as cursor:
            return await cursor.fetchall()

async def get_all_user_ids():
    async with db_session() as db:
        # Use UNION to get unique IDs from both registered users and those who only pressed /start
        async with db.execute("SELECT user_id FROM users UNION SELECT user_id FROM bot_starters") as cursor:
            return [r[0] for r in await cursor.fetchall()]

async def get_user_ids_by_role(role):
    async with db_session() as db:
        async with db.execute("SELECT user_id FROM users WHERE role = ?", (role,)) as cursor:
            return [r[0] for r in await cursor.fetchall()]

async def get_revenue_stats():
    async with db_session() as db:
        async with db.execute("SELECT SUM(price) FROM orders WHERE status = 'finished'") as c:
            total_rev = (await c.fetchone())[0] or 0
        async with db.execute("SELECT SUM(amount) FROM transactions WHERE type = 'out' AND description LIKE '%komissiya%'") as c:
            total_prof = abs((await c.fetchone())[0] or 0)
        return {"revenue": total_rev, "profit": total_prof}

async def get_user_stats_rich(user_id):
    async with db_session() as db:
        # Total trips (finished)
        async with db.execute("SELECT COUNT(*) FROM orders WHERE (passenger_id = ? OR driver_id = ?) AND status = 'finished'", (user_id, user_id)) as c:
            trips = (await c.fetchone())[0]
            
        # Total referrals
        async with db.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)) as c:
            referrals = (await c.fetchone())[0]
            
        return {"trips": trips, "referrals": referrals}

def calculate_loyalty_level(trips):
    if trips >= 100: return 'level_vip'
    if trips >= 50: return 'level_gold'
    if trips >= 20: return 'level_silver'
    return 'level_bronze'

async def update_user_profile(user_id, full_name=None, phone=None):
    async with db_session() as db:
        if full_name: await db.execute("UPDATE users SET full_name = ? WHERE user_id = ?", (full_name, user_id))
        if phone: await db.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        await db.commit()

async def add_rating(order_id, p_id, d_id, stars, comment=None, badges=None):
    async with db_session() as db:
        cursor = await db.execute("INSERT OR IGNORE INTO ratings (order_id, passenger_id, driver_id, stars, comment, badges) VALUES (?, ?, ?, ?, ?, ?)", (order_id, p_id, d_id, stars, comment, badges))
        if cursor.rowcount == 0:
            return False # Already rated
        
        # Increment badge counters in drivers table
        if badges:
            badge_list = badges.split(',')
            if 'fast' in badge_list:
                await db.execute("UPDATE drivers SET badge_fast = badge_fast + 1 WHERE user_id = ?", (d_id,))
            if 'clean' in badge_list:
                await db.execute("UPDATE drivers SET badge_clean = badge_clean + 1 WHERE user_id = ?", (d_id,))
            if 'polite' in badge_list:
                await db.execute("UPDATE drivers SET badge_polite = badge_polite + 1 WHERE user_id = ?", (d_id,))

        # Update driver rating average
        async with db.execute("SELECT AVG(stars) FROM ratings WHERE driver_id = ?", (d_id,)) as c:
            avg = (await c.fetchone())[0]
            await db.execute("UPDATE drivers SET rating = ? WHERE user_id = ?", (avg, d_id))
        await db.commit()

async def set_referral(user_id, referrer_id):
    async with db_session() as db:
        # Avoid self-referral and check if already referred
        if user_id != referrer_id:
            async with db.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,)) as c:
                if not (await c.fetchone())[0]:
                    await db.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
                    await db.commit()

async def get_upcoming_scheduled_orders():
    async with db_session() as db:
        # In a real app we'd parse the date string, but for simplicity:
        async with db.execute("SELECT * FROM orders WHERE status = 'pending' AND scheduled_time IS NOT NULL AND notified = 0") as c:
            return await c.fetchall()

async def mark_order_notified(order_id):
    async with db_session() as db:
        await db.execute("UPDATE orders SET notified = 1 WHERE order_id = ?", (order_id,))
        await db.commit()

async def get_all_users_raw():
    async with db_session() as db:
        async with db.execute("SELECT * FROM users") as cursor: return await cursor.fetchall()

async def get_all_orders_raw():
    async with db_session() as db:
        async with db.execute("SELECT * FROM orders") as cursor: return await cursor.fetchall()

async def get_all_transactions_raw():
    async with db_session() as db:
        async with db.execute("SELECT * FROM transactions") as cursor: return await cursor.fetchall()

async def get_global_stats():
    async with db_session() as db:
        async with db.execute("SELECT COUNT(user_id) FROM (SELECT user_id FROM users UNION SELECT user_id FROM bot_starters)") as c: 
            users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM drivers WHERE is_approved = 1") as c: drivers = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM orders") as c: orders = (await c.fetchone())[0]
        async with db.execute("SELECT SUM(price) FROM orders WHERE status = 'finished'") as c: rev = (await c.fetchone())[0] or 0
        return {
            "total_users": users,
            "active_drivers": drivers,
            "total_orders": orders,
            "total_revenue": rev
        }

async def get_driver_sub_status(user_id):
    async with db_session() as db:
        async with db.execute("SELECT subscription_expiry, pax_quota, parcel_quota FROM drivers WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row: return None
            
            expiry, pax, pc = row
            is_active = False
            if expiry:
                try:
                    is_active = datetime.fromisoformat(str(expiry)) > datetime.now()
                except: pass
            
            return {
                "is_active": is_active,
                "expiry": expiry,
                "pax_quota": pax or 0,
                "parcel_quota": pc or 0
            }



async def get_orders_by_date_range(start_date: str, end_date: str, role: str = None):
    """Get orders filtered by date range. Dates in YYYY-MM-DD format."""
    async with db_session() as db:
        query = "SELECT * FROM orders WHERE date(timestamp) BETWEEN ? AND ? ORDER BY timestamp DESC"
        async with db.execute(query, (start_date, end_date)) as cursor:
            return await cursor.fetchall()

async def get_users_by_role_raw(role: str = None):
    """Get users optionally filtered by role. Joins with drivers if role is driver."""
    async with db_session() as db:
        if role == 'driver':
            query = """
                SELECT u.*, d.car_name, d.car_number, d.car_class, d.rating, d.total_rides 
                FROM users u 
                LEFT JOIN drivers d ON u.user_id = d.user_id 
                WHERE u.role = 'driver' 
                ORDER BY u.reg_date DESC
            """
            async with db.execute(query) as c:
                return await c.fetchall()
        elif role:
            async with db.execute("SELECT * FROM users WHERE role = ? ORDER BY reg_date DESC", (role,)) as c:
                return await c.fetchall()
        else:
            async with db.execute("SELECT * FROM users ORDER BY reg_date DESC") as c:
                return await c.fetchall()

async def get_user_full_report(user_id: int):
    """Get all data for a specific user: profile, orders, transactions."""
    async with db_session() as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as c:
            user = await c.fetchone()
        async with db.execute("SELECT * FROM orders WHERE passenger_id = ? OR driver_id = ? ORDER BY timestamp DESC", (user_id, user_id)) as c:
            orders = await c.fetchall()
        async with db.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp DESC", (user_id,)) as c:
            transactions = await c.fetchall()
        driver_info = None
        async with db.execute("SELECT * FROM drivers WHERE user_id = ?", (user_id,)) as c:
            driver_info = await c.fetchone()
        return user, orders, transactions, driver_info



async def get_weekly_leaderboard():
    async with db_session() as db:
        sql = """
            SELECT driver_id, COUNT(*) as ride_count, u.full_name
            FROM orders o
            JOIN users u ON o.driver_id = u.user_id
            WHERE o.status = 'finished' 
              AND o.timestamp >= date('now', '-7 days')
            GROUP BY driver_id
            ORDER BY ride_count DESC
            LIMIT 10
        """
        async with db.execute(sql) as cursor:
            return await cursor.fetchall()

async def get_driver_rank(user_id):
    async with db_session() as db:
        sql = """
            SELECT rank FROM (
                SELECT driver_id, ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) as rank
                FROM orders
                WHERE status = 'finished' AND timestamp >= date('now', '-7 days')
                GROUP BY driver_id
            ) WHERE driver_id = ?
        """
        async with db.execute(sql, (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def grant_leaderboard_prizes(limit=1, amount=10000):
    winners = await get_weekly_leaderboard()
    if not winners: return []
    
    awarded = []
    async with db_session() as db:
        for i, (d_id, count, name) in enumerate(winners[:limit]):
            await update_user_balance_conn(db, d_id, amount, f"Weekly Leaderboard Prize (Rank #{i+1})", 'in')
            awarded.append((d_id, name))
        await db.commit()
    return awarded

async def update_order_live_location_msg(order_id, msg_id):
    async with db_session() as db:
        await db.execute("UPDATE orders SET live_loc_msg_id = ? WHERE order_id = ?", (msg_id, order_id))
        await db.commit()

async def is_priority_driver(user_id):
    async with db_session() as db:
        sql = "SELECT priority_expiry FROM drivers WHERE user_id = ? AND priority_expiry > datetime('now')"
        async with db.execute(sql, (user_id,)) as cursor:
            row = await cursor.fetchone()
            return True if row else False

async def get_online_drivers_priority_data():
    async with db_session() as db:
        sql = """
            SELECT user_id, 
                   (CASE WHEN priority_expiry > datetime('now') THEN 1 ELSE 0 END) as has_priority,
                   work_type,
                   active_route,
                   lat,
                   lon
            FROM drivers 
            WHERE is_online = 1 AND is_approved = 1
        """
        async with db.execute(sql) as cursor:
            return await cursor.fetchall()

async def set_driver_work_type(user_id, work_type):
    async with db_session() as db:
        await db.execute("UPDATE drivers SET work_type = ? WHERE user_id = ?", (work_type, user_id))
        await db.commit()

async def purchase_priority(user_id, days, amount):
    async with db_session() as db:
        # Get current expiry
        async with db.execute("SELECT priority_expiry FROM drivers WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            current_expiry = row[0] if row and row[0] else None
        
        from datetime import datetime, timedelta
        now = datetime.now()
        if current_expiry:
            try: start_dt = max(now, datetime.fromisoformat(str(current_expiry)))
            except: start_dt = now
        else:
            start_dt = now
            
        new_expiry = (start_dt + timedelta(days=days)).isoformat()
        
        await update_user_balance_conn(db, user_id, -amount, f"Priority purchased ({days} days)", 'out')
        await db.execute("UPDATE drivers SET priority_expiry = ? WHERE user_id = ?", (new_expiry, user_id))
        await db.commit()
        return new_expiry

# --- Promocodes Helpers ---
async def add_promocode(code: str, amount: float, usage_limit: int, expiry_date: str = None):
    async with db_session() as db:
        sql = "INSERT INTO promocodes (code, amount, usage_limit, expiry_date) VALUES (?, ?, ?, ?)"
        try:
            await db.execute(sql, (code.upper(), amount, usage_limit, expiry_date))
            await db.commit()
            return True
        except Exception as e:
            logging.error(f"Error adding promocode {code}: {e}")
            return False

async def get_all_promocodes():
    async with db_session() as db:
        sql = "SELECT code, amount, usage_limit, used_count, expiry_date FROM promocodes ORDER BY code"
        async with db.execute(sql) as cursor:
            return await cursor.fetchall()

async def delete_promocode(code: str):
    async with db_session() as db:
        await db.execute("DELETE FROM promocodes WHERE code = ?", (code.upper(),))
        await db.commit()

AUTO_REPLIES_CACHE = None

# --- Auto Replies Helpers ---
async def add_auto_reply(keyword: str, reply: str):
    global AUTO_REPLIES_CACHE
    async with db_session() as db:
        await db.execute("INSERT OR REPLACE INTO auto_replies (keyword, reply) VALUES (?, ?)", (keyword.lower().strip(), reply))
        await db.commit()
        AUTO_REPLIES_CACHE = None

async def get_all_auto_replies():
    async with db_session() as db:
        async with db.execute("SELECT id, keyword, reply FROM auto_replies ORDER BY keyword") as cursor:
            return await cursor.fetchall()

async def delete_auto_reply(reply_id: int):
    global AUTO_REPLIES_CACHE
    async with db_session() as db:
        await db.execute("DELETE FROM auto_replies WHERE id = ?", (reply_id,))
        await db.commit()
        AUTO_REPLIES_CACHE = None

async def clear_all_auto_replies():
    global AUTO_REPLIES_CACHE
    async with db_session() as db:
        await db.execute("DELETE FROM auto_replies")
        await db.commit()
        AUTO_REPLIES_CACHE = None

async def find_auto_reply(text: str):
    """Finds a matching auto-reply by checking if keyword is in text"""
    global AUTO_REPLIES_CACHE
    if not text: return None
    text = text.lower().strip()
    
    if AUTO_REPLIES_CACHE is None:
        async with db_session() as db:
            async with db.execute("SELECT keyword, reply FROM auto_replies") as cursor:
                AUTO_REPLIES_CACHE = await cursor.fetchall()
                
    best_match = None
    for kw, rep in AUTO_REPLIES_CACHE:
        if kw in text:
            if not best_match or len(kw) > len(best_match[0]):
                best_match = (kw, rep)
    return best_match[1] if best_match else None

# --- Logs Helpers ---
async def log_action(admin_id: int, action: str, details: str = ""):
    async with db_session() as db:
        sql = "INSERT INTO logs (admin_id, action, details) VALUES (?, ?, ?)"
        await db.execute(sql, (admin_id, action, details))
        await db.commit()

# --- Logging Helpers ---

# --- Deposits Helpers ---
async def add_deposit(user_id: int, amount: float, photo_id: str):
    async with db_session() as db:
        sql = "INSERT INTO deposits (user_id, amount, photo_id) VALUES (?, ?, ?)"
        cursor = await db.execute(sql, (user_id, amount, photo_id))
        await db.commit()
        return cursor.lastrowid

async def get_pending_deposits():
    async with db_session() as db:
        sql = """
            SELECT d.*, u.full_name 
            FROM deposits d 
            JOIN users u ON d.user_id = u.user_id 
            WHERE d.status = 'pending' 
            ORDER BY d.timestamp DESC
        """
        async with db.execute(sql) as cursor:
            return await cursor.fetchall()

async def get_deposit(deposit_id: int):
    async with db_session() as db:
        sql = "SELECT * FROM deposits WHERE id = ?"
        async with db.execute(sql, (deposit_id,)) as cursor:
            return await cursor.fetchone()

async def update_deposit_status(deposit_id: int, status: str):
    async with db_session() as db:
        await db.execute("UPDATE deposits SET status = ? WHERE id = ?", (status, deposit_id))
        await db.commit()



async def get_pending_parcels():
    async with db_session() as db:
        async with db.execute("SELECT * FROM orders WHERE status = 'pending' AND order_type = 'parcel' ORDER BY timestamp DESC") as cursor:
            return await cursor.fetchall()

async def delete_targeted_charity(charity_id: int):
    async with db_session() as db:
        await db.execute("DELETE FROM targeted_charities WHERE id = ?", (charity_id,))
        await db.commit()


async def get_nearby_drivers(lat: float, lon: float, radius_km: float = 20.0):
    """Get online approved drivers within radius_km of the given coordinates using Haversine."""
    import math
    async with db_session() as db:
        sql = """
            SELECT d.user_id, u.full_name, d.car_name, d.car_number,
                   d.lat, d.lon, d.rating
            FROM drivers d
            JOIN users u ON d.user_id = u.user_id
            WHERE d.is_online = 1
              AND d.is_approved = 1
              AND d.lat IS NOT NULL
              AND d.lon IS NOT NULL
        """
        async with db.execute(sql) as cursor:
            rows = await cursor.fetchall()

    # Filter by distance using Haversine formula
    R = 6371.0  # Earth radius in km
    nearby = []
    for row in rows:
        uid, name, car, plate, d_lat, d_lon, rating = row
        try:
            dlat = math.radians(d_lat - lat)
            dlon = math.radians(d_lon - lon)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat)) * math.cos(math.radians(d_lat)) * math.sin(dlon/2)**2
            dist = R * 2 * math.asin(math.sqrt(a))
            if dist <= radius_km:
                nearby.append((uid, name, car, plate, d_lat, d_lon, rating or 5.0, dist))
        except (TypeError, ValueError):
            continue

    nearby.sort(key=lambda x: x[7])  # Sort by distance
    return nearby

async def save_user_address(user_id: int, address: str):
    """Saves or updates a manually entered address for a user."""
    if len(address) > 100 or len(address) < 2:
        return
    async with db_session() as db:
        await db.execute("""
            INSERT INTO saved_addresses (user_id, address, usage_count, last_used)
            VALUES (?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, address) DO UPDATE SET
                usage_count = usage_count + 1,
                last_used = CURRENT_TIMESTAMP
        """, (user_id, address))
        await db.commit()

async def get_saved_addresses(user_id: int, limit: int = 5):
    """Returns the most used/recent addresses for a user."""
    async with db_session() as db:
        async with db.execute("""
            SELECT address FROM saved_addresses 
            WHERE user_id = ? 
            ORDER BY usage_count DESC, last_used DESC 
            LIMIT ?
        """, (user_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def get_pending_parcels(limit: int = 10) -> list:
    """Returns active pending parcel orders."""
    async with db_session() as db:
        async with db.execute("""
            SELECT order_id, from_location, to_location, price, timestamp, parcel_photo
            FROM orders
            WHERE order_type = 'parcel' AND status = 'pending'
            ORDER BY order_id DESC LIMIT ?
        """, (limit,)) as cursor:
            return await cursor.fetchall()


# ==========================================
# 💺 HAMROH / POPUTCHIK REYSLARI FUNKSIYALARI
# ==========================================

async def create_ride(driver_id: int, from_location: str, to_location: str, departure_time: str, 
                      total_seats: int, price_per_seat: float, car_model: str, car_number: str, notes: str = "") -> int:
    """Yangi hamroh/reys e'lonini yaratadi."""
    async with db_session() as db:
        cursor = await db.execute("""
            INSERT INTO rides (driver_id, from_location, to_location, departure_time, 
                               total_seats, available_seats, price_per_seat, car_model, car_number, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """, (driver_id, from_location, to_location, departure_time, total_seats, total_seats, price_per_seat, car_model, car_number, notes))
        await db.commit()
        return cursor.lastrowid

async def get_active_rides(from_location: str = None, to_location: str = None, limit: int = 20) -> list:
    """Faol va bo'sh o'rindiqlari bor reyslarni qaytaradi."""
    async with db_session() as db:
        query = """
            SELECT r.ride_id, r.driver_id, r.from_location, r.to_location, r.departure_time,
                   r.total_seats, r.available_seats, r.price_per_seat, r.car_model, r.car_number,
                   r.notes, r.created_at, u.full_name, u.phone, d.rating
            FROM rides r
            JOIN users u ON r.driver_id = u.user_id
            LEFT JOIN drivers d ON r.driver_id = d.user_id
            WHERE r.status = 'active' AND r.available_seats > 0
        """
        params = []
        if from_location:
            query += " AND r.from_location LIKE ?"
            params.append(f"%{from_location}%")
        if to_location:
            query += " AND r.to_location LIKE ?"
            params.append(f"%{to_location}%")
            
        query += " ORDER BY r.ride_id DESC LIMIT ?"
        params.append(limit)
        
        async with db.execute(query, tuple(params)) as cursor:
            return await cursor.fetchall()

async def get_ride(ride_id: int):
    """Bitta reys haqida to'liq ma'lumotni oladi."""
    async with db_session() as db:
        async with db.execute("""
            SELECT r.ride_id, r.driver_id, r.from_location, r.to_location, r.departure_time,
                   r.total_seats, r.available_seats, r.price_per_seat, r.car_model, r.car_number,
                   r.notes, r.status, r.created_at, u.full_name, u.phone, d.rating
            FROM rides r
            JOIN users u ON r.driver_id = u.user_id
            LEFT JOIN drivers d ON r.driver_id = d.user_id
            WHERE r.ride_id = ?
        """, (ride_id,)) as cursor:
            return await cursor.fetchone()

async def book_ride_seats(ride_id: int, passenger_id: int, seats_count: int = 1) -> tuple:
    """Reysdan o'rindiqlarni band qiladi."""
    async with db_session() as db:
        async with db.execute("SELECT available_seats, status, driver_id FROM rides WHERE ride_id = ?", (ride_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False, "Reys topilmadi."
            avail, status, driver_id = row
            if status != 'active':
                return False, "Ushbu reys yakunlangan yoki bekor qilingan."
            if avail < seats_count:
                return False, f"Yetarli bo'sh joy yo'q. Qolgan joylar: {avail} ta."
            if passenger_id == driver_id:
                return False, "Haydovchi o'z reysidan joy band qila olmaydi."

        # Deduct seats and create booking atomically
        new_avail = avail - seats_count
        await db.execute("UPDATE rides SET available_seats = ? WHERE ride_id = ?", (new_avail, ride_id))
        cursor = await db.execute("""
            INSERT INTO ride_bookings (ride_id, passenger_id, seats_count, status)
            VALUES (?, ?, ?, 'confirmed')
        """, (ride_id, passenger_id, seats_count))
        await db.commit()
        return True, cursor.lastrowid

async def cancel_ride(ride_id: int, driver_id: int) -> bool:
    """Haydovchi reysni bekor qiladi."""
    async with db_session() as db:
        cursor = await db.execute("""
            UPDATE rides SET status = 'cancelled' 
            WHERE ride_id = ? AND driver_id = ? AND status = 'active'
        """, (ride_id, driver_id))
        await db.commit()
        return cursor.rowcount > 0

async def cancel_ride_booking(booking_id: int, passenger_id: int) -> bool:
    """Yo'lovchi o'z bronini bekor qiladi va o'rindiqlarni qaytaradi."""
    async with db_session() as db:
        async with db.execute("SELECT ride_id, seats_count, status FROM ride_bookings WHERE booking_id = ? AND passenger_id = ?", 
                              (booking_id, passenger_id)) as cursor:
            row = await cursor.fetchone()
            if not row or row[2] != 'confirmed':
                return False
            ride_id, seats, _ = row

        await db.execute("UPDATE ride_bookings SET status = 'cancelled' WHERE booking_id = ?", (booking_id,))
        await db.execute("UPDATE rides SET available_seats = available_seats + ? WHERE ride_id = ?", (seats, ride_id))
        await db.commit()
        return True

async def get_driver_active_rides(driver_id: int) -> list:
    """Haydovchining faol reyslarini qaytaradi."""
    async with db_session() as db:
        async with db.execute("""
            SELECT ride_id, from_location, to_location, departure_time, total_seats, available_seats, price_per_seat, status, created_at
            FROM rides 
            WHERE driver_id = ? AND status = 'active'
            ORDER BY ride_id DESC
        """, (driver_id,)) as cursor:
            return await cursor.fetchall()

async def get_ride_bookings(ride_id: int) -> list:
    """Bitta reysga band qilingan barcha yo'lovchilarni oladi."""
    async with db_session() as db:
        async with db.execute("""
            SELECT rb.booking_id, rb.passenger_id, rb.seats_count, rb.status, rb.created_at,
                   u.full_name, u.phone
            FROM ride_bookings rb
            JOIN users u ON rb.passenger_id = u.user_id
            WHERE rb.ride_id = ? AND rb.status = 'confirmed'
        """, (ride_id,)) as cursor:
            return await cursor.fetchall()

async def get_user_ride_bookings(passenger_id: int) -> list:
    """Yo'lovchining faol reys bronlarini oladi."""
    async with db_session() as db:
        async with db.execute("""
            SELECT rb.booking_id, rb.ride_id, rb.seats_count, rb.created_at,
                   r.from_location, r.to_location, r.departure_time, r.price_per_seat,
                   r.car_model, r.car_number, u.full_name as driver_name, u.phone as driver_phone
            FROM ride_bookings rb
            JOIN rides r ON rb.ride_id = r.ride_id
            JOIN users u ON r.driver_id = u.user_id
            WHERE rb.passenger_id = ? AND rb.status = 'confirmed' AND r.status = 'active'
            ORDER BY rb.booking_id DESC
        """, (passenger_id,)) as cursor:
            return await cursor.fetchall()

# ==========================================
# 🔄 POPUTKA / QAYTISHGA YO'LOVCHI FUNKSIYALARI
# ==========================================

async def set_driver_return_trip(driver_id: int, from_loc: str, to_loc: str, return_time: str) -> int:
    """Haydovchining qaytish yo'nalishini saqlaydi."""
    async with db_session() as db:
        # Avvalgi faollarni o'chirib yangisini yozamiz
        await db.execute("UPDATE return_trips SET status = 'expired' WHERE driver_id = ? AND status = 'active'", (driver_id,))
        cursor = await db.execute("""
            INSERT INTO return_trips (driver_id, from_location, to_location, available_from_time, status)
            VALUES (?, ?, ?, ?, 'active')
        """, (driver_id, from_loc, to_loc, return_time))
        await db.commit()
        return cursor.lastrowid

async def get_active_return_trips(from_loc: str = None, to_loc: str = None) -> list:
    """Mos keluvchi qaytish safarlarini topadi."""
    async with db_session() as db:
        query = """
            SELECT rt.id, rt.driver_id, rt.from_location, rt.to_location, rt.available_from_time,
                   u.full_name, u.phone, d.car_name, d.car_number, d.rating
            FROM return_trips rt
            JOIN users u ON rt.driver_id = u.user_id
            JOIN drivers d ON rt.driver_id = d.user_id
            WHERE rt.status = 'active'
        """
        params = []
        if from_loc:
            query += " AND rt.from_location LIKE ?"
            params.append(f"%{from_loc}%")
        if to_loc:
            query += " AND rt.to_location LIKE ?"
            params.append(f"%{to_loc}%")
            
        async with db.execute(query, tuple(params)) as cursor:
            return await cursor.fetchall()

async def close_return_trip(driver_id: int):
    """Haydovchi qaytish safarini yakunlaydi."""
    async with db_session() as db:
        await db.execute("UPDATE return_trips SET status = 'completed' WHERE driver_id = ? AND status = 'active'", (driver_id,))
        await db.commit()


async def reset_all_orders() -> int:
    """Admin: Barcha buyurtmalarni bazadan o'chiradi. O'chirilgan buyurtmalar sonini qaytaradi."""
    async with db_session() as db:
        async with db.execute("SELECT COUNT(*) FROM orders") as c:
            total = (await c.fetchone())[0] or 0
        await db.execute("DELETE FROM orders")
        await db.commit()
        return total


async def get_system_deep_audit() -> dict:
    """Performs a 360-degree deep audit of all users, drivers, orders, groups, and channels."""
    async with db_session() as db:
        # 1. Users
        async with db.execute("SELECT COUNT(*) FROM bot_starters") as c:
            total_starters = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_registered = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM users WHERE role = 'passenger'") as c:
            total_passengers = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM users WHERE role = 'driver'") as c:
            total_drivers = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM users WHERE status = 'blocked'") as c:
            blocked_users = (await c.fetchone())[0] or 0
        async with db.execute("SELECT language, COUNT(*) FROM users GROUP BY language") as c:
            lang_stats = dict(await c.fetchall())
        async with db.execute("SELECT SUM(balance), SUM(cashback_balance) FROM users") as c:
            row = await c.fetchone()
            total_balance = (row[0] if row and row[0] is not None else 0.0)
            total_cashback = (row[1] if row and row[1] is not None else 0.0)

        # 2. Drivers
        async with db.execute("SELECT COUNT(*) FROM drivers WHERE is_approved = 1") as c:
            approved_drivers = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM drivers WHERE is_online = 1") as c:
            online_drivers = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM drivers WHERE car_class = 'Comfort'") as c:
            comfort_drivers = (await c.fetchone())[0] or 0
        async with db.execute("SELECT AVG(rating) FROM drivers WHERE rating > 0") as c:
            avg_rating = (await c.fetchone())[0] or 5.0

        # 3. Orders
        async with db.execute("SELECT COUNT(*) FROM orders") as c:
            total_orders = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM orders WHERE status = 'finished'") as c:
            finished_orders = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM orders WHERE status = 'cancelled'") as c:
            cancelled_orders = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM orders WHERE status IN ('pending', 'accepted', 'arrived')") as c:
            active_orders = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM orders WHERE order_type = 'taxi'") as c:
            taxi_orders = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM orders WHERE order_type = 'parcel'") as c:
            parcel_orders = (await c.fetchone())[0] or 0
        async with db.execute("SELECT SUM(price), AVG(price) FROM orders WHERE status = 'finished'") as c:
            row = await c.fetchone()
            total_turnover = (row[0] if row and row[0] is not None else 0.0)
            avg_order_price = (row[1] if row and row[1] is not None else 0.0)

        # 4. Groups
        async with db.execute("SELECT chat_id, title, is_order_channel, is_parcel_channel FROM groups") as c:
            groups_list = await c.fetchall()
            total_groups = len(groups_list)
            order_groups_count = sum(1 for g in groups_list if g[2] == 1)
            parcel_groups_count = sum(1 for g in groups_list if g[3] == 1)

        # 5. Channels
        async with db.execute("SELECT channel_id, invite_link, is_active FROM channels") as c:
            channels_list = await c.fetchall()
            total_channels = len(channels_list)
            active_channels_count = sum(1 for ch in channels_list if ch[2] == 1)

        # 6. Rides / Poputka
        try:
            async with db.execute("SELECT COUNT(*) FROM rides WHERE status = 'active'") as c:
                active_rides = (await c.fetchone())[0] or 0
        except Exception:
            active_rides = 0

        return {
            "total_starters": total_starters,
            "total_registered": total_registered,
            "total_passengers": total_passengers,
            "total_drivers": total_drivers,
            "approved_drivers": approved_drivers,
            "online_drivers": online_drivers,
            "comfort_drivers": comfort_drivers,
            "avg_driver_rating": round(avg_rating, 2),
            "blocked_users": blocked_users,
            "lang_stats": lang_stats,
            "total_balance": total_balance,
            "total_cashback": total_cashback,
            "total_orders": total_orders,
            "finished_orders": finished_orders,
            "cancelled_orders": cancelled_orders,
            "active_orders": active_orders,
            "taxi_orders": taxi_orders,
            "parcel_orders": parcel_orders,
            "total_turnover": total_turnover,
            "avg_order_price": round(avg_order_price, 2),
            "total_groups": total_groups,
            "order_groups_count": order_groups_count,
            "parcel_groups_count": parcel_groups_count,
            "groups_list": groups_list,
            "total_channels": total_channels,
            "active_channels_count": active_channels_count,
            "channels_list": channels_list,
            "active_rides": active_rides
        }


async def get_orders_deep_analysis() -> dict:
    """Returns comprehensive 100% analytics of orders with route stats and revenue."""
    async with db_session() as db:
        # 1. Total counts
        async with db.execute("SELECT COUNT(*) FROM orders") as c:
            total_orders = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM orders WHERE DATE(timestamp) = DATE('now')") as c:
            today_orders = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM orders WHERE order_type = 'taxi'") as c:
            taxi_count = (await c.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM orders WHERE order_type = 'parcel'") as c:
            parcel_count = (await c.fetchone())[0] or 0
            
        # 2. Status counts
        async with db.execute("SELECT status, COUNT(*) FROM orders GROUP BY status") as c:
            status_dict = dict(await c.fetchall())
            
        pending_cnt = status_dict.get('pending', 0)
        active_cnt = status_dict.get('accepted', 0) + status_dict.get('arrived', 0)
        finished_cnt = status_dict.get('finished', 0)
        cancelled_cnt = status_dict.get('cancelled', 0)
        
        # 3. Revenue
        async with db.execute("SELECT SUM(price), AVG(price) FROM orders WHERE status = 'finished'") as c:
            row = await c.fetchone()
            total_revenue = (row[0] if row and row[0] is not None else 0.0)
            avg_price = (row[1] if row and row[1] is not None else 0.0)
            
        async with db.execute("SELECT SUM(price) FROM orders WHERE status = 'finished' AND DATE(timestamp) = DATE('now')") as c:
            today_revenue = (await c.fetchone())[0] or 0.0

        # 4. Top 5 Routes
        async with db.execute("""
            SELECT from_location, to_location, COUNT(*) as cnt, AVG(price) as avg_p
            FROM orders
            GROUP BY from_location, to_location
            ORDER BY cnt DESC
            LIMIT 5
        """) as c:
            top_routes = await c.fetchall()

        # 5. Car Class breakdown
        async with db.execute("SELECT car_class, COUNT(*) FROM orders GROUP BY car_class") as c:
            class_dict = dict(await c.fetchall())

        return {
            "total_orders": total_orders,
            "today_orders": today_orders,
            "taxi_count": taxi_count,
            "parcel_count": parcel_count,
            "pending_count": pending_cnt,
            "active_count": active_cnt,
            "finished_count": finished_cnt,
            "cancelled_count": cancelled_cnt,
            "total_revenue": total_revenue,
            "today_revenue": today_revenue,
            "avg_price": round(avg_price, 2),
            "top_routes": top_routes,
            "class_dict": class_dict
        }


