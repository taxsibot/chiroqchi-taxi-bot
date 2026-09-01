from aiogram import Router, types
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_user
import uuid

router = Router()

@router.inline_query()
async def inline_invite_handler(query: types.InlineQuery):
    user_id = query.from_user.id
    bot_info = await query.bot.get_me()
    
    # Generate referral link
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    
    # Invitation content
    title = "🚕 Chiroqchi Taksi — Taklifnoma"
    description = "Sizni eng tezkor taksi xizmatiga taklif qilaman! ✨"
    
    msg_text = (
        f"<b>🚕 Chiroqchi Taksi — Sizning ishonchli hamrohingiz!</b>\n\n"
        f"Do'stim, sizni Chiroqchi bo'ylab va viloyatlararo eng tezkor, arzon va xavfsiz taksi xizmatidan foydalanishga taklif qilaman! 🚀\n\n"
        f"✅ <b>Nega aynan biz?</b>\n"
        f"• ⏱ Mashina topish judayam tez\n"
        f"• 💰 Narxlar hamyonbop va adolatli\n"
        f"• 🎁 Har bir taklif uchun bonuslar\n"
        f"• 🛡 Xavfsiz va ishonchli haydovchilar\n\n"
        f"Siz ham hoziroq ro'yxatdan o'ting va imkoniyatlardan bahramand bo'ling! 👇"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Botni ishga tushirish", url=ref_link)]
    ])
    
    # Create result article
    result_id: str = str(uuid.uuid4())
    result = InlineQueryResultArticle(
        id=result_id,
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(
            message_text=msg_text,
            parse_mode="HTML"
        ),
        reply_markup=kb,
        thumbnail_url="https://raw.githubusercontent.com/aiogram/aiogram/dev-3.x/docs/static/img/logo.png"
    )
    
    await query.answer(results=[result], cache_time=300, is_personal=True)
