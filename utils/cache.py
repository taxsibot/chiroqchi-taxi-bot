import asyncio
import time

# Subscription check cache
# {user_id: (timestamp, has_started, is_subscribed)}
SUB_CACHE = {}

# User warning cooldowns
# {user_id: timestamp}
USER_WARNING_COOLDOWN = {}

# Chat warning cooldowns
# {chat_id: timestamp}
CHAT_WARNING_COOLDOWN = {}

# Tracking warning messages to delete them when user starts the bot
# {user_id: [(chat_id, message_id), ...]}
WARNING_MESSAGES = {}

# Group Guard Status Cache
# {chat_id: (timestamp, is_guarded)}
GROUP_GUARD_CACHE = {}

# User Started Status Cache
# {user_id: (timestamp, has_started)}
USER_STARTED_CACHE = {}


# Active channels cache
# (timestamp, channels_list)
CHANNELS_CACHE = (0, [])
CHANNELS_CACHE_TTL = 300 # 5 minutes

# Cache duration for message events (5 minutes)
CACHE_DURATION = 300

# Cache duration for callback_query events (10 minutes)
# Callbacks are button presses — less risky to cache longer
CALLBACK_CACHE_DURATION = 600

# User warning cooldown (5 minutes)
USER_WARNING_TIME = 300

# Chat warning cooldown (1 minute)
CHAT_WARNING_TIME = 60

# --- Language Cache ---
# {user_id: (timestamp, lang_code)}
LANG_CACHE: dict[int, tuple[float, str]] = {}
LANG_CACHE_TTL = 300  # 5 minutes

# --- Auto-reply Cache ---
# (timestamp, {keyword: reply}) - full table cached
AUTO_REPLY_CACHE: tuple[float, dict[str, str]] = (0.0, {})
AUTO_REPLY_CACHE_TTL = 120  # 2 minutes

async def cleanup_caches():
    """
    Background task that periodically removes expired entries from all in-memory caches.
    Prevents unbounded memory growth in long-running bots.
    Runs every 30 minutes.
    """
    global AUTO_REPLY_CACHE
    while True:
        await asyncio.sleep(1800) # Run every 30 minutes
        now = time.time()
        
        expired_sub = [uid for uid, val in SUB_CACHE.items()
                       if isinstance(val, tuple) and (now - val[0]) > 3600]
        for uid in expired_sub:
            SUB_CACHE.pop(uid, None)

        expired_user_warn = [uid for uid, ts in USER_WARNING_COOLDOWN.items()
                             if (now - ts) > USER_WARNING_TIME * 2]
        for uid in expired_user_warn:
            USER_WARNING_COOLDOWN.pop(uid, None)

        expired_chat_warn = [cid for cid, ts in CHAT_WARNING_COOLDOWN.items()
                             if (now - ts) > CHAT_WARNING_TIME * 2]
        for cid in expired_chat_warn:
            CHAT_WARNING_COOLDOWN.pop(cid, None)

        # Clean language cache
        expired_lang = [uid for uid, val in LANG_CACHE.items()
                        if (now - val[0]) > LANG_CACHE_TTL * 2]
        for uid in expired_lang:
            LANG_CACHE.pop(uid, None)

        # Reset auto-reply cache if stale
        if (now - AUTO_REPLY_CACHE[0]) > AUTO_REPLY_CACHE_TTL * 2:
            AUTO_REPLY_CACHE = (0.0, {})

        # Clean Group Guard and User Started caches
        expired_guard = [cid for cid, val in GROUP_GUARD_CACHE.items() if (now - val[0]) > 3600]
        for cid in expired_guard: GROUP_GUARD_CACHE.pop(cid, None)
        
        expired_started = [uid for uid, val in USER_STARTED_CACHE.items() if (now - val[0]) > 1800]
        for uid in expired_started: USER_STARTED_CACHE.pop(uid, None)
