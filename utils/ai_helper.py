from google import genai
from google.genai import types as genai_types
from config import GEMINI_API_KEY
import logging
from database.db import get_setting

logger = logging.getLogger(__name__)

# Initialize Client
client = None
if GEMINI_API_KEY:
    try:
        from config import USE_PROXY, PROXY_URL
        if USE_PROXY and PROXY_URL:
            import os
            os.environ['http_proxy'] = PROXY_URL
            os.environ['https_proxy'] = PROXY_URL
            logger.info(f"AI using proxy: {PROXY_URL}")
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini AI client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")


async def _build_system_prompt() -> str:
    """Builds a dynamic system prompt from DB settings."""
    min_price   = await get_setting('min_price', '5000')
    comm_rate   = await get_setting('commission_rate_taxi', '10')
    ref_bonus   = await get_setting('ref_bonus', '500')
    min_bal     = await get_setting('min_driver_balance', '20000')
    admin_url   = await get_setting('admin_url', 'https://t.me/Admeral2002')

    return f"""Sen "Chiroqchi Taksi" platformasining Universal AI Yordamchisisan.
Sen haqiqiy sun'iy intellekt kabi ishlaysan — har qanday savol, mavzu va muammoga javob bera olasan.

━━━━━━━━━━━━━━━━━━━━
📌 PLATFORMA HAQIDA (asosiy ma'lumotlar):
━━━━━━━━━━━━━━━━━━━━
• Xizmatlar: Taksi (yo'lovchi tashish) va Pochta (yuk yetkazish)
• Hudud: Chiroqchi tumani va butun O'zbekiston
• Narxlar: Minimal {min_price} so'm — yo'lovchi narxni o'zi belgilaydi (auktsion)
• Haydovchi komissiyasi: {comm_rate}%
• Haydovchi minimal balansi: {min_bal} so'm
• Referal bonus: do'stni taklif uchun {ref_bonus} so'm
• Admin: {admin_url}
• Ro'yxatdan o'tish: /start → Bot orqali

━━━━━━━━━━━━━━━━━━━━
🌍 UMUMIY BILIM:
━━━━━━━━━━━━━━━━━━━━
• Senda jahon bo'yicha to'liq bilim mavjud — fan, texnologiya, tarix, madaniyat, biznes, tibbiyot va boshqalar
• Har qanday savol bo'yicha aniq va foydali javob ber
• O'zbek, rus va ingliz tillarida muloqot qilishga tayyor bo'l

━━━━━━━━━━━━━━━━━━━━
💬 MULOQOT USLUBI:
━━━━━━━━━━━━━━━━━━━━
• Do'stona, professional va qisqa javoblar ber
• Mavzuga mos emojilar ishlatish (🚕📦💰🌍🤖✨)
• Javoblarni strukturali (ro'yxat, bold) formatlash
• Suhbatni "Suhbatni tugatish" tugmasi bosilguncha davom ettir
• Oxirida adminga yo'naltirma — faqat foydalanuvchi o'zi xohlasa
• MUHIM: Har bir javob oxirida "❓ Yana savolingiz bormi?" qo'shma
"""


async def get_ai_response(
    user_query: str,
    history: list,
    user_lang: str = 'uz'
) -> tuple[str, list]:
    """
    Multi-turn AI conversation.
    """
    if not client:
        logger.warning("AI client not initialized (check GEMINI_API_KEY)")
        return None, history

    import asyncio
    try:
        system_prompt = await _build_system_prompt()

        # Format history
        formatted_history = []
        for msg in history:
            formatted_history.append(
                genai_types.Content(
                    role=msg['role'],
                    parts=[genai_types.Part(text=msg['text'])]
                )
            )

        # We use asyncio.to_thread because the genai Client is synchronous by default
        # and we want to avoid blocking the main event loop.
        def _get_response():
            try:
                chat = client.chats.create(
                    model='gemini-2.0-flash',
                    config=genai_types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.7,
                        max_output_tokens=1024,
                    ),
                    history=formatted_history
                )
                return chat.send_message(user_query)
            except Exception as e:
                logger.error(f"Sync AI Call Error: {e}")
                raise e

        logger.info(f"Sending request to Gemini AI: {user_query[:50]}...")
        try:
            # Add a timeout to prevent hanging forever
            response = await asyncio.wait_for(asyncio.to_thread(_get_response), timeout=30.0)
        except asyncio.TimeoutError:
            logger.error("Gemini AI call timed out after 30 seconds")
            return None, history

        if response and response.text:
            ai_text = response.text.strip()
            logger.info("Gemini AI response received successfully")
            updated_history = history + [
                {'role': 'user',  'text': user_query},
                {'role': 'model', 'text': ai_text},
            ]
            if len(updated_history) > 20:
                updated_history = updated_history[-20:]
            return ai_text, updated_history

        logger.error("Gemini returned empty response")
        return None, history

    except Exception as e:
        logger.error(f"Gemini AI Error: {e}")
        return None, history
