import aiohttp
import logging
from database.db import get_setting

logger = logging.getLogger(__name__)

async def send_sms(phone: str, text: str):
    """
    Sends SMS using Eskiz.uz API.
    Requires 'eskiz_email' and 'eskiz_password' (or 'eskiz_token') in settings.
    """
    email = await get_setting('eskiz_email', '')
    password = await get_setting('eskiz_password', '')
    token = await get_setting('eskiz_token', '')

    if not (token or (email and password)):
        logger.warning("SMS not sent: Eskiz.uz credentials missing in settings.")
        return False

    # Standardize phone (998901234567)
    phone = phone.replace('+', '').replace(' ', '')
    if len(phone) == 9:
        phone = "998" + phone

    try:
        async with aiohttp.ClientSession() as session:
            # Get token if not provided
            if not token:
                auth_url = "https://notify.eskiz.uz/api/auth/login"
                async with session.post(auth_url, data={'email': email, 'password': password}) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        token = res.get('data', {}).get('token', '')
                        # Cache token? No, for simplicity we just fetch it or use the saved one
                    else:
                        logger.error(f"Eskiz.uz Login Failed: {resp.status}")
                        return False

            if not token: return False

            # Send SMS
            headers = {'Authorization': f'Bearer {token}'}
            payload = {
                'mobile_phone': phone,
                'message': text,
                'from': '4546', # Standard Eskiz 'from' number
                'callback_url': ''
            }
            send_url = "https://notify.eskiz.uz/api/message/sms/send"
            async with session.post(send_url, headers=headers, data=payload) as resp:
                if resp.status == 200:
                    logger.info(f"SMS sent to {phone}")
                    return True
                else:
                    res_text = await resp.text()
                    logger.error(f"Eskiz.uz Send Failed ({resp.status}): {res_text}")
                    return False
    except Exception as e:
        logger.error(f"SMS Error: {e}")
        return False
