import re
import asyncio
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Uzbekistan car plate regex patterns (simplified for OCR extraction)
# 1: 01A001AA (Private)
# 2: 01001AAA (Legal)
UZB_PLATE_REGEX = r'([0-9]{2}[A-Z][0-9]{3}[A-Z]{2})|([0-9]{2}[0-9]{3}[A-Z]{3})'

_reader = None
reader = None  # Compatibility alias

def get_reader():
    global _reader
    if _reader is None:
        try:
            import easyocr
            logger.info("Initializing EasyOCR reader in background...")
            _reader = easyocr.Reader(['en'], gpu=False)
            logger.info("EasyOCR reader initialized successfully.")
        except Exception as e:
            logger.warning(f"EasyOCR could not be loaded: {e}")
            _reader = False
    return _reader if _reader is not False else None

def normalize_plate(text: str) -> str:
    """Removes all non-alphanumeric characters and converts to uppercase."""
    return re.sub(r'[^0-9A-Z]', '', text.upper())

def normalize_for_comparison(text: str) -> str:
    """Extra normalization for robust comparison (e.g. treating O and 0 as the same)."""
    text = normalize_plate(text)
    # Treat common OCR confusions as the same character for comparison
    return text.replace('O', '0').replace('I', '1').replace('Z', '2').replace('S', '5').replace('B', '8')

async def extract_plate_number(photo_bytes: bytes, entered_plate: str = None) -> str:
    """
    Extracts Uzbekistan car plate number from image bytes.
    If entered_plate is provided, checks if it exists in the image.
    Returns the normalized plate string or None.
    """
    reader = get_reader()
    if reader is None:
        return None
    try:
        # Convert bytes to opencv image
        nparr = np.frombuffer(photo_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return None
            
        # --- Preprocessing to improve OCR ---
        # 1. Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 2. Resizing for better visibility
        height, width = gray.shape
        if width < 1200:
            scale = 1200 / width
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            
        # 3. Increase Contrast
        gray = cv2.convertScaleAbs(gray, alpha=1.5, beta=0)
        
        # We will try both original and preprocessed images
        imgs_to_try = [img, gray]
        
        for trial_img in imgs_to_try:
            results = await asyncio.to_thread(reader.readtext, trial_img)
            
            # Combine all text
            all_text = "".join([normalize_plate(res[1]) for res in results])
            
            # If we know what we're looking for, check for substring match
            if entered_plate:
                norm_entered = normalize_for_comparison(entered_plate)
                norm_all = normalize_for_comparison(all_text)
                if norm_entered in norm_all:
                    return entered_plate
            
            # 1. Direct block matches
            for (bbox, text, prob) in results:
                normalized = normalize_plate(text)
                # Try with O/0 replacement for regex matching
                lenient = normalized.replace('O', '0')
                match = re.search(UZB_PLATE_REGEX, lenient)
                if match:
                    return match.group(0)
            
            # 2. Combined text matches (if plate is split)
            all_text_lenient = all_text.replace('O', '0')
            match = re.search(UZB_PLATE_REGEX, all_text_lenient)
            if match:
                return match.group(0)
                
        return None
    except Exception as e:
        logger.error(f"OCR Error extracting plate: {e}")
        return None

async def extract_receipt_amount(photo_bytes: bytes) -> int:
    """
    Tries to find the payment amount in a receipt photo (Click, Payme, Uzum, Apelsin).
    Looks for patterns like 'Summa', 'To'landi', 'Muvaffaqiyatli', 'UZS', etc.
    """
    reader = get_reader()
    if reader is None:
        return None
    try:
        nparr = np.frombuffer(photo_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
            
        results = await asyncio.to_thread(reader.readtext, img)
        full_text = " ".join([res[1] for res in results])
        
        # Enhanced regex patterns for Uzbek payment apps
        patterns = [
            r'(?:summa|to[\'’`]?landi|oplata|amount|itogo|jami|perevod)[:\s]*([\d\s\.,]+)',
            r'([\d\s\.,]+)\s*(?:so[\'’`]?m|uzs|sum)',
            r'(\d{1,3}(?:[ ,.]\d{3})+)\s*(?:so[\'’`]?m|uzs|sum)?',
            r'\b(\d{4,7})\b'
        ]
        
        found_amounts = []
        for pattern in patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            for m in matches:
                clean_num = re.sub(r'[^\d]', '', m)
                if clean_num and len(clean_num) >= 4:
                    val = int(clean_num)
                    # Filter sensible deposit bounds (e.g. 5,000 to 5,000,000 UZS)
                    if 5000 <= val <= 10000000 and val not in [2026, 2025, 2024, 8600, 9860]:
                        found_amounts.append(val)
        
        if found_amounts:
            # Usually the highest amount matching typical top-up bounds is the total payment
            return max(found_amounts)
        return None
    except Exception as e:
        logger.error(f"OCR Error extracting receipt amount: {e}")
        return None


def validate_uzb_plate(text: str) -> bool:
    """Checks if the string follows UZB plate format."""
    normalized = normalize_plate(text)
    return bool(re.fullmatch(UZB_PLATE_REGEX, normalized))
