import json
import os
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

logger = logging.getLogger(__name__)

def get_region(loc_text: str) -> str:
    """
    Kiritilgan manzil matnidan uning qaysi viloyatga (Toshkent yoki Qashqadaryo) 
    tegishli ekanligini aniqlaydi.
    """
    if not loc_text:
        return "other"
        
    text_lower = loc_text.lower()
    
    try:
        # data/locations.json ni o'qish
        json_path = os.path.join('data', 'locations.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            locs = json.load(f)
            tosh_words = locs.get("toshkent", [])
            qash_words = locs.get("qashqadaryo", [])
            
            # Agar tekst ichida Toshkent so'zlari bo'lsa
            if any(w.lower() in text_lower for w in tosh_words):
                return "toshkent"
                
            # Agar tekst ichida Qashqadaryo so'zlari bo'lsa
            if any(w.lower() in text_lower for w in qash_words):
                return "qashqadaryo"
    except Exception as e:
        logger.error(f"Error reading locations.json in route_helper: {e}")
        
    return "other"

def get_order_route(from_loc, to_loc):
    f_reg = get_region(from_loc)
    t_reg = get_region(to_loc)
    
    if f_reg == "toshkent" and t_reg == "qashqadaryo":
        return "toshkent-qashqadaryo"
    elif f_reg == "qashqadaryo" and t_reg == "toshkent":
        return "qashqadaryo-toshkent"
    elif f_reg == t_reg and f_reg != "other":
        return "intra"
    return "all"

# --- CENTRALIZED LOCATIONS & ROUTE HELPERS ---

LOCATIONS = {
    "🏙 TOSHKENT TUMANLARI": [
        "🏙 Toshkent", "🏙 Chilonzor",
        "🏙 Yunusobod", "🏙 Olmazor",
        "🏙 Mirzo Ulug'bek", "🏙 Sergeli",
        "🏙 Yashnobod", "🏙 Uchtepa",
        "🏙 Shayxontohur", "🏙 Yakkasaroy",
        "🏙 Bektemir", "🏙 Yangihayot",
        "🏙 Qo'yliq", "🏙 Ippodrom"
    ],
    "📍 QASHQADARYO TUMANLARI": [
        "📍 Chiroqchi", "📍 Ko'kdala",
        "📍 Qarshi", "📍 Shahrisabz",
        "📍 Kitob", "📍 Yakkabog'",
        "📍 Qamashi", "📍 G'uzor",
        "📍 Koson", "📍 Kasbi",
        "📍 Muborak", "📍 Dehqonobod",
        "📍 Nishon", "📍 Mirishkor"
    ],
    "🏘 CHIROQCHI HUDUDLARI": [
        "📍 Yangi Chiroqchi", "📍 Ayritom",
        "📍 Dam", "📍 Jar",
        "📍 Pakandi", "📍 Umakay",
        "📍 Karlik", "📍 Kattabog'",
        "📍 Toqbuloq", "📍 Talisoch",
        "📍 Dardoq", "📍 Chiyal",
        "📍 Maymanoq", "📍 Pudina",
        "📍 Qovchin", "📍 Langar"
    ],
    "🏢 BOSHQA VILOYATLAR": [
        "🏢 Samarqand", "🏢 Buxoro",
        "🏢 Navoiy", "🏢 Jizzax",
        "🏢 Termiz", "🏢 Andijon"
    ]
}

async def get_location_keyboard(step: str, user_id: int, lang: str = 'uz', prefix: str = "loc_") -> InlineKeyboardMarkup:
    """Generate universal inline keyboard with location buttons organized by regions."""
    from database.db import get_saved_addresses
    from utils.locales import get_trans
    
    buttons = []
    
    # 1. Saved Addresses
    saved = await get_saved_addresses(user_id)
    if saved:
        buttons.append([InlineKeyboardButton(text="⭐ SAQLANGAN MANZILLAR", callback_data=f"{prefix}none")])
        row_saved = []
        for addr in saved[:4]:
            row_saved.append(InlineKeyboardButton(text=f"✨ {addr}", callback_data=f"{prefix}{step}_{addr}"))
            if len(row_saved) == 2:
                buttons.append(row_saved)
                row_saved = []
        if row_saved:
            buttons.append(row_saved)

    # 2. Predefined LOCATIONS categorized by region
    for region, places in LOCATIONS.items():
        buttons.append([InlineKeyboardButton(text=f"━━ {region} ━━", callback_data=f"{prefix}none")])
        row = []
        for place in places:
            display_name = place
            clean_name = place.replace("📍 ", "").replace("🏙 ", "").replace("🏢 ", "")
            row.append(InlineKeyboardButton(text=display_name, callback_data=f"{prefix}{step}_{clean_name}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
            
    buttons.append([InlineKeyboardButton(text="✏️ " + get_trans(lang, 'write_manually'), callback_data=f"{prefix}{step}_custom")])
    buttons.append([InlineKeyboardButton(text="🔙 " + get_trans(lang, 'back'), callback_data=f"{prefix}back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)



async def get_estimated_price(from_loc, to_loc, car_class='Standard'):
    """
    Analyzes the route and class to provide a base estimated price.
    Includes dynamic night-time surge pricing from settings.
    """
    from database.db import get_setting
    route = get_order_route(from_loc, to_loc)
    
    if route in ["toshkent-qashqadaryo", "qashqadaryo-toshkent"]:
        base = 120000
    elif route == "intra":
        base = 40000
    else:
        base = 60000 # Default/Unknown
        
    if car_class == 'Comfort':
        base = base * 1.25 # 25% premium for comfort
        
    # Night surge (23:00 - 06:00)
    is_night_enabled = (await get_setting('is_night_surge_enabled', '1')) == '1'
    if is_night_enabled:
        now_hour = datetime.now().hour
        if now_hour >= 23 or now_hour < 6:
            multiplier = float(await get_setting('night_surge_multiplier', '1.2'))
            base = base * multiplier
        
    return int(round(base, -3)) # Round to nearest 1000


