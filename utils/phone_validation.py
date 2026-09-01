import re

def is_uzbek_number(phone_str: str) -> bool:
    """
    Validates if the phone number is a valid Uzbekistan number (+998 ...).
    Accepts: +998901234567, 998901234567, 901234567.
    Normalized to: +998XXXXXXXXX.
    """
    if not phone_str or not isinstance(phone_str, str):
        return False
        
    # Remove all non-digit characters except '+'
    cleaned = re.sub(r'[^\d+]', '', phone_str)
    
    # Check formats
    if cleaned.startswith('+998'):
        return len(cleaned) == 13
    elif cleaned.startswith('998'):
        return len(cleaned) == 12
    elif len(cleaned) == 9:
        return True
    elif len(cleaned) == 10 and cleaned.startswith('8'):
        return True
    
    return False

def normalize_phone(phone_str: str) -> str:
    """Normalizes the number to +998XXXXXXXXX format."""
    if not phone_str or not isinstance(phone_str, str):
        return ""
        
    cleaned = re.sub(r'[^\d]', '', phone_str)
    
    # Handle 890... (10 digits) -> convert to 99890...
    if len(cleaned) == 10 and cleaned.startswith('8'):
        cleaned = '998' + cleaned[1:]
        
    if cleaned.startswith('998'):
        return '+' + cleaned
    if len(cleaned) == 9:
        return '+998' + cleaned
        
    return '+' + cleaned if '+' not in phone_str else phone_str
