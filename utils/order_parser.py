import re

def parse_order_text(text: str):
    """
    Parses natural language text to extract order details.
    Expected patterns (Uzbek):
    - [Location]dan -> from_loc
    - [Location]ga -> to_loc
    - [Number] [kishi/odam] -> passenger_count
    - [Number] [so'm/ming] -> price
    """
    text = text.lower()
    
    # 1. From Location ([City]dan)
    from_match = re.search(r"([a-z'‘]+)dan", text)
    from_loc = from_match.group(1).capitalize() if from_match else None
    
    # 2. To Location ([City]ga)
    to_match = re.search(r"([a-z'‘]+)ga", text)
    to_loc = to_match.group(1).capitalize() if to_match else None
    
    # 3. Passenger Count
    pax_match = re.search(r"(\d+)\s*(?:kishi|odam|pax)", text)
    if pax_match:
        pax_count = int(pax_match.group(1))
    else:
        # Check for word-based numbers
        words = {
            "bir": 1, "bitta": 1,
            "ikki": 2, "ikkita": 2,
            "uch": 3, "uchta": 3,
            "to'rt": 4, "to'rtta": 4
        }
        pax_count = 1 # Default
        for word, val in words.items():
            if word in text:
                pax_count = val
                break
                
    # 4. Price
    # Matches "100 000", "100000", "100 ming"
    price_match = re.search(r"(\d+[\s\d]*)\s*(?:so'm|som|ming|k\b)", text)
    price = 0
    if price_match:
        raw_price = price_match.group(1).replace(" ", "")
        price = int(raw_price)
        # If "ming" follows (e.g., 100 ming)
        if "ming" in text and price < 5000:
            price *= 1000
    else:
        # Fallback for just "yuz ming", "ellik ming" etc.
        price_words = {
            "yuz ming": 100000,
            "ellik ming": 50000,
            "sakson ming": 80000,
            "to'qson ming": 90000,
            "yetmish ming": 70000,
            "oltmish ming": 60000,
            "qirq ming": 40000,
            "o'ttiz ming": 30000,
            "yigirma ming": 20000
        }
        for word, val in price_words.items():
            if word in text:
                price = val
                break

    return {
        "from_loc": from_loc,
        "to_loc": to_loc,
        "price": price,
        "passenger_count": pax_count,
        "type": "parcel" if "pochta" in text or "posilka" in text else "taxi"
    }
