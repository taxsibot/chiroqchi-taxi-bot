import logging
import json
import re
import asyncio
from datetime import datetime, timedelta
from google.genai import types as genai_types
from utils.ai_helper import client
from utils.route_helper import LOCATIONS, get_estimated_price

logger = logging.getLogger(__name__)

# Dialect & Slang normalizer dictionary
DIALECT_MAP = {
    # Tashkent variants
    "toshkan": "toshkent", "toshkanga": "toshkentga", "toshkandan": "toshkentdan",
    "toshtent": "toshkent", "toshkint": "toshkent", "tashkent": "toshkent",
    "tashkenta": "toshkent", "tashkente": "toshkent", "tash": "toshkent",
    # Chiroqchi variants
    "chirokchi": "chiroqchi", "chirakchi": "chiroqchi", "chirikchi": "chiroqchi",
    "chiroqchig'a": "chiroqchiga", "chiroqchidang": "chiroqchidan", "chiroqchidin": "chiroqchidan",
    "chiroqchiga": "chiroqchiga", "chiroqchidan": "chiroqchidan", "chirachi": "chiroqchi",
    # Shahrisabz
    "shahrisabiz": "shahrisabz", "shahrisapz": "shahrisabz", "shaxrisabz": "shahrisabz", "shaxrisapz": "shahrisabz",
    "shahrisabzga": "shahrisabzga", "shahrisabzdan": "shahrisabzdan",
    # Samarqand
    "samarqan": "samarqand", "samarkand": "samarqand", "samarqanga": "samarqandga", "samarkanda": "samarqand",
    # Qarshi
    "karshi": "qarshi", "karshiga": "qarshiga", "qarshig'a": "qarshiga",
    # Qashqadaryo
    "qashqadaryog'a": "qashqadaryoga", "qashqadaryodin": "qashqadaryodan", "kashkadarya": "qashqadaryo",
    # Ayritom
    "ayratom": "ayritom", "aritom": "ayritom", "airitom": "ayritom", "ayritomga": "ayritomga",
    # Dam
    "damga": "damga", "damdan": "damdan",
    # Qamashi
    "kamashi": "qamashi", "kamashiga": "qamashiga",
    # Kitob
    "kitap": "kitob", "kitobga": "kitobga",
    # Guzar
    "guzor": "g'uzor", "ghuzor": "g'uzor", "guzorga": "g'uzorga",
    # Kokdala
    "kokdala": "ko'kdala", "kukdala": "ko'kdala", "kokdalaga": "ko'kdalaga",
    # Muborak
    "mubarek": "muborak", "muborakka": "muborakka",
    # Words
    "bita": "bitta", "ikkta": "ikkita", "uchta": "uchta", "torta": "to'rtta",
    "posilka": "pochta", "bervorgan": "pochta", "bervorish": "pochta", "bervoryapmiz": "pochta",
    "yuvorish": "yuborish", "yetkazish": "pochta", "dastavka": "pochta"
}

# Known locations for precision lookup
KNOWN_LOCATIONS = [
    # Chiroqchi & Qashqadaryo
    "chiroqchi", "chiroqchi shahar", "yangi chiroqchi", "ayritom", "dam", "jar",
    "pakandi", "umakay", "karlik", "kattabog'", "kattabog", "toqbuloq", "talisoch",
    "dardoq", "chiyal", "urmonjon", "ayribobo", "yangiobod", "ozodlik", "paxtakor",
    "maymanoq", "pudina", "qovchin", "xo'jaobod", "xonto'ra", "qorabuloq", "langar",
    "shahrisabz", "yakkabog'", "yakkabog", "ko'kdala", "kokdala",
    "qamashi", "qarshi", "kitob", "koson", "g'uzor", "guzor", "muborak", "mubarek",
    "kasbi", "nishon", "mirishkor", "dehqonobod", "qashqadaryo",
    # Toshkent tumanlari & bekatlari
    "toshkent", "tashkent", "chilonzor", "yunusobod", "olmazor", "mirzo ulug'bek",
    "sergeli", "yashnobod", "uchtepa", "shayxontohur", "yakkasaroy", "bektemir",
    "yangihayot", "qo'yliq", "ippodrom",
    # Boshqa viloyatlar
    "samarqand", "samarkand", "buxoro", "bukhara",
    "navoiy", "navoi", "jizzax", "jizzakh", "sirdaryo", "guliston",
    "andijon", "farg'ona", "namangan", "termiz", "surxondaryo", "nukus", "urganch"
]


def clean_loc_name(name: str) -> str:
    """Format and capitalize location name properly."""
    name = name.strip()
    clean = re.sub(r'(dan|ga|da|ni|ning|ден|дан|га|ге|го|до|из|в|от|ka|qa)$', '', name, flags=re.IGNORECASE).strip()
    if not clean:
        clean = name
    return clean.capitalize()

def normalize_text_dialects(text: str) -> str:
    """Replaces dialect and slang words with standard location names."""
    words = text.lower().split()
    normalized = []
    for w in words:
        # Strip punctuation
        clean_w = re.sub(r'[^\w\'`]', '', w)
        if clean_w in DIALECT_MAP:
            normalized.append(DIALECT_MAP[clean_w])
        else:
            normalized.append(w)
    return " ".join(normalized)

def parse_order_rules(text: str) -> dict:
    """
    High-speed, 100% offline rule-based Natural Language Processing engine with dialect support.
    """
    if not text or len(text.strip()) < 3:
        return None
        
    t_lower = normalize_text_dialects(text)
    
    # 1. Check for negative / non-order patterns
    non_order_greetings = ["salom", "assalomu alaykum", "qandaysiz", "raxmat", "rahmat", "admin", "yordam", "stop", "privet", "hello"]
    if t_lower in non_order_greetings or t_lower.startswith("/"):
        return None

    # 2. Determine Order Type (Taxi vs Parcel)
    parcel_keywords = ["pochta", "posilka", "yuk", "hujjat", "bervorgan", "berib yuborish", "quti", "sumka", "dori", "paket", "посылка", "доставка", "груз", "передать", "вещи"]
    is_parcel = any(k in t_lower for k in parcel_keywords)
    order_type = "parcel" if is_parcel else "taxi"

    # 3. Detect Locations (from_loc & to_loc)
    from_loc = None
    to_loc = None
    
    # Pattern A: Suffix based (e.g. "Chiroqchidan Toshkentga", "Toshkentdan Samarqandga")
    match_from = re.search(r'([a-zA-Z\']{3,20})(?:dan|ден)\b', t_lower)
    match_to = re.search(r'([a-zA-Z\']{3,20})(?:ga|ka|qa|ге|га)\b', t_lower)
    
    if match_from:
        candidate_from = match_from.group(1)
        for loc in KNOWN_LOCATIONS:
            if candidate_from in loc or loc in candidate_from:
                from_loc = clean_loc_name(loc)
                break
        if not from_loc:
            from_loc = candidate_from.capitalize()

    if match_to:
        candidate_to = match_to.group(1)
        for loc in KNOWN_LOCATIONS:
            if candidate_to in loc or loc in candidate_to:
                to_loc = clean_loc_name(loc)
                break
        if not to_loc:
            to_loc = candidate_to.capitalize()

    # Pattern B: Preposition / Dash based (e.g. "Toshkent - Chiroqchi", "iz Tashkenta v Chirakchi")
    if not from_loc or not to_loc:
        dash_match = re.search(r'([a-zA-Z\']{3,20})\s*[-—–➔➡️>]\s*([a-zA-Z\']{3,20})', t_lower)
        if dash_match:
            from_loc = clean_loc_name(dash_match.group(1))
            to_loc = clean_loc_name(dash_match.group(2))

    # Pattern C: Location scan
    found_known = []
    for loc in KNOWN_LOCATIONS:
        pattern = r'\b' + re.escape(loc)
        if re.search(pattern, t_lower):
            clean = clean_loc_name(loc)
            if clean not in found_known:
                found_known.append(clean)
                
    if len(found_known) >= 2:
        if not from_loc: from_loc = found_known[0]
        if not to_loc: to_loc = found_known[1]
    elif len(found_known) == 1:
        single_loc = found_known[0]
        if "toshkent" in single_loc.lower():
            if "toshkentdan" in t_lower:
                from_loc = "Toshkent"
                to_loc = "Chiroqchi"
            else:
                from_loc = "Chiroqchi"
                to_loc = "Toshkent"
        else:
            to_loc = single_loc
            from_loc = "Chiroqchi" if single_loc.lower() != "chiroqchi" else "Toshkent"

    # If no locations found, not an order
    if not from_loc and not to_loc:
        return None

    if not from_loc: from_loc = "Chiroqchi"
    if not to_loc: to_loc = "Toshkent"

    # 4. Extract Passenger Count
    passengers = 1
    pax_match = re.search(r'(\d+)\s*(?:ta\s*)?(?:kishi|odam|joy|kishilik|человек|мест[ао]?)', t_lower)
    if pax_match:
        try:
            passengers = int(pax_match.group(1))
        except:
            passengers = 1
    else:
        words_pax = {"bitta": 1, "ikkita": 2, "uchta": 3, "to'rtta": 4, "tortta": 4, "odin": 1, "dva": 2, "tri": 3}
        for w, count in words_pax.items():
            if w in t_lower:
                passengers = count
                break

    # 5. Extract Price
    price = None
    price_match = re.search(r'(\d{1,3}(?:[ .]\d{3})+|\d+)\s*(?:ming|k|тыс|so[\'’`]?m|som|сум)?', t_lower)
    if price_match:
        raw_val = price_match.group(1).replace(" ", "").replace(".", "")
        try:
            val = int(raw_val)
            if "ming" in t_lower or "k" in t_lower or "тыс" in t_lower:
                if val < 1000:
                    val = val * 1000
            if 5000 <= val <= 2000000 and val not in [2024, 2025, 2026]:
                price = val
        except:
            pass

    # 6. Extract Time & Date
    now = datetime.now()
    date_str = now.strftime("%d.%m.%Y")
    time_str = "Hozir"
    
    if "ertaga" in t_lower or "zavtra" in t_lower:
        date_str = (now + timedelta(days=1)).strftime("%d.%m.%Y")
        time_str = "Ertalab"
    elif "indin" in t_lower:
        date_str = (now + timedelta(days=2)).strftime("%d.%m.%Y")

    time_match = re.search(r'(?:soat\s*)?(\d{1,2}(?::\d{2})?)\s*(?:da|ga|lar|gacha|boshi|kechki|ertalab)?', t_lower)
    if time_match:
        t_cand = time_match.group(1)
        if ":" in t_cand or ("soat" in t_lower and int(t_cand.split(":")[0]) <= 24):
            time_str = t_cand

    return {
        "is_order": True,
        "order_type": order_type,
        "from_loc": from_loc,
        "to_loc": to_loc,
        "passengers": max(1, min(passengers, 8)),
        "price": price,
        "date": date_str,
        "time": time_str,
        "parcel_description": "Pochta / Yuk" if is_parcel else None
    }


PARSE_PROMPT = """Sening vazifang foydalanuvchi yozgan matn yoki ovozli xabaridan Taksi yoki Pochta buyurtmasi ma'lumotlarini aniqlash va FAQAT JSON formatida qaytarishdir.

JSON strukturasi:
{{
  "is_order": true yoki false (agar xabar buyurtma bo'lmasa false qaytar),
  "order_type": "taxi" yoki "parcel",
  "from_loc": "qayerdan (boshlang'ich manzil)",
  "to_loc": "qayerga (borish manzili)",
  "passengers": odam soni (integer, default 1),
  "price": taklif qilingan narx (integer yoki null),
  "date": "KK.OO.YYYY" (agar aytilmagan bo'lsa bugungi sana),
  "time": "SS:DD yoki Hozir",
  "parcel_description": "pochta nimaligi yoki null"
}}

Qoidalar:
1. Faqat JSON formatda javob ber, hech qanday ortiqcha matn qo'shma.
2. Agar boshlang'ich manzil aytilmagan bo'lsa, "Chiroqchi" deb ol.
3. Bugungi sana: {current_date}
"""

async def parse_smart_order(text: str = None, voice_file_path: str = None) -> dict:
    """
    Dual-engine smart order parser with instant dialect NLP and Gemini AI.
    """
    if text:
        rule_result = parse_order_rules(text)
        if rule_result and rule_result.get("is_order"):
            if not rule_result.get("price") and rule_result.get("from_loc") and rule_result.get("to_loc"):
                rule_result["price"] = await get_estimated_price(rule_result["from_loc"], rule_result["to_loc"])
            return rule_result

    if client:
        current_date = datetime.now().strftime("%d.%m.%Y")
        try:
            parts = [PARSE_PROMPT.format(current_date=current_date)]
            
            if text:
                parts.append(f"Foydalanuvchi xabari: {text}")
            
            if voice_file_path:
                with open(voice_file_path, "rb") as f:
                    audio_data = f.read()
                parts.append(genai_types.Part.from_bytes(data=audio_data, mime_type="audio/ogg"))
                parts.append("Ushbu ovozli xabardan buyurtma ma'lumotlarini ajratib ol.")

            def _call_gemini():
                return client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=parts,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type='application/json',
                        temperature=0.1
                    )
                )

            response = await asyncio.to_thread(_call_gemini)
            if response and response.text:
                data = json.loads(response.text)
                if data.get("is_order"):
                    if not data.get("price") and data.get("from_loc") and data.get("to_loc"):
                        data["price"] = await get_estimated_price(data["from_loc"], data["to_loc"])
                    return data
        except Exception as e:
            logger.error(f"Gemini Smart Order Parser Error: {e}")

    if text:
        return parse_order_rules(text)

    return None
