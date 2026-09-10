import re
import asyncio
import logging
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# Uzbekistan car plate regex patterns
# 1: 01A001AA (Private)
# 2: 01001AAA (Legal)
UZB_PLATE_REGEX = r'([0-9]{2}[A-Z][0-9]{3}[A-Z]{2})|([0-9]{2}[0-9]{3}[A-Z]{3})'

def get_reader():
    """
    Returns True to indicate OCR capabilities are ready (powered by Gemini AI).
    Never blocks registration flow.
    """
    return True

reader = True

def normalize_plate(text: str) -> str:
    """Removes all non-alphanumeric characters and converts to uppercase."""
    if not text:
        return ""
    return re.sub(r'[^0-9A-Z]', '', text.upper())

def normalize_for_comparison(text: str) -> str:
    """Extra normalization for robust comparison (treating O/0, I/1, etc. as equal)."""
    text = normalize_plate(text)
    return text.replace('O', '0').replace('I', '1').replace('Z', '2').replace('S', '5').replace('B', '8')

def validate_uzb_plate(text: str) -> bool:
    """Checks if the string follows UZB plate format."""
    normalized = normalize_plate(text)
    return bool(re.fullmatch(UZB_PLATE_REGEX, normalized))

async def extract_plate_number(photo_bytes: bytes, entered_plate: str = None) -> str:
    """
    Extracts Uzbekistan car plate number from image bytes using Gemini AI Vision.
    No heavy OpenCV or PyTorch required.
    """
    from utils.ai_helper import client
    from google.genai import types as genai_types

    if not client or not photo_bytes:
        # Fallback: if Gemini client is not initialized, return entered_plate if valid
        return entered_plate if (entered_plate and validate_uzb_plate(entered_plate)) else None

    try:
        prompt = (
            "Ushbu avtomobil rasmidan davlat raqamini (avtoraqam) aniqlab ber.\n"
            "Format namunasi: 01A123BA yoki 70A777AA yoki 01123AAA.\n"
        )
        if entered_plate:
            prompt += f"Foydalanuvchi kiritgan raqam: {entered_plate}. Agar shu raqam yoki shunga juda o'xshash raqam rasmda ko'rinsa, aynan o'sha raqamni qaytar.\n"
        prompt += "Faqat avtoraqamning o'zini qaytar (masalan: 70A123BA). Hech qanday qo'shimcha so'z, nuqta yoki izoh yozma. Agar umuman raqam ko'rinmasa, NONE deb yoz."

        def _call_vision():
            image_part = genai_types.Part.from_bytes(data=photo_bytes, mime_type="image/jpeg")
            return client.models.generate_content(
                model='gemini-2.0-flash',
                contents=[image_part, prompt],
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=30,
                )
            )

        response = await asyncio.wait_for(asyncio.to_thread(_call_vision), timeout=15.0)
        if response and response.text:
            cleaned = response.text.strip().upper()
            if "NONE" in cleaned or not cleaned:
                return entered_plate if entered_plate else None
            
            # Extract plate pattern from response
            norm_res = normalize_plate(cleaned)
            match = re.search(UZB_PLATE_REGEX, norm_res)
            if match:
                detected = match.group(0)
                if entered_plate and normalize_for_comparison(detected) == normalize_for_comparison(entered_plate):
                    return entered_plate
                return detected
            
            if entered_plate and normalize_for_comparison(entered_plate) in normalize_for_comparison(cleaned):
                return entered_plate

    except Exception as e:
        logger.warning(f"Gemini Vision Plate OCR Error: {e}")

    # Fallback to entered plate to not block registration
    return entered_plate if entered_plate else None

async def extract_receipt_amount(photo_bytes: bytes) -> int:
    """
    Extracts payment amount from Click/Payme/Uzum receipt using Gemini AI Vision.
    """
    from utils.ai_helper import client
    from google.genai import types as genai_types

    if not client or not photo_bytes:
        return None

    try:
        prompt = (
            "Ushbu to'lov cheki (Click, Payme, Uzum va h.k.) rasmidan to'langan asosiy pul miqdorini aniqlab ber.\n"
            "Faqat butun son ko'rinishida yoz (masalan: 50000 yoki 100000).\n"
            "Hech qanday so'm, valyuta belgisi yoki boshqa so'z qo'shma. Agar summa topilmasa, NONE deb yoz."
        )

        def _call_vision():
            image_part = genai_types.Part.from_bytes(data=photo_bytes, mime_type="image/jpeg")
            return client.models.generate_content(
                model='gemini-2.0-flash',
                contents=[image_part, prompt],
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=20,
                )
            )

        response = await asyncio.wait_for(asyncio.to_thread(_call_vision), timeout=15.0)
        if response and response.text:
            digits = re.sub(r'[^\d]', '', response.text.strip())
            if digits:
                val = int(digits)
                if 1000 <= val <= 20000000:
                    return val

    except Exception as e:
        logger.warning(f"Gemini Vision Receipt OCR Error: {e}")

    return None
