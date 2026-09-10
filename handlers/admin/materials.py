from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from utils.states import AdminStates
from database.db import get_setting, update_setting, log_action
from .base import admin_filter

router = Router()

@router.callback_query(F.data == "adm_promo_mtl", admin_filter)
async def adm_materials_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    
    current_banner = await get_setting('promo_banner_id', None)
    
    text = "<b>🖼 REKLAMA MATERIALLARI</b>\n━━━━━━━━━━━━━━\nBu yerdagi rasm foydalanuvchilarning referal menyusi va boshqa reklama qismlarida ko'rsatiladi.\n\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Yangi rasm yuklash", callback_data="add_promo_mtl")],
        [InlineKeyboardButton(text="🔙 Ortga", callback_data="adm_main")]
    ])
    
    if current_banner:
        text += "✅ Hozirda tizimda rasm o'rnatilgan."
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer_photo(photo=current_banner, caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        text += "❌ Hozircha rasm o'rnatilmagan."
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "add_promo_mtl", admin_filter)
async def add_materials_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.adding_promo_material)
    
    # If the previous message was a photo, we can't edit text easily, so we delete and send
    if callback.message.photo:
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer("<b>🖼 YANGI RASM YUKLASH</b>\n━━━━━━━━━━━━━━\nIltimos, botga yangi banner rasmini yuboring:",
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_promo_mtl")]]),
                                      parse_mode="HTML")
    else:
        await callback.message.edit_text("<b>🖼 YANGI RASM YUKLASH</b>\n━━━━━━━━━━━━━━\nIltimos, botga yangi banner rasmini yuboring:",
                                      reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_promo_mtl")]]),
                                      parse_mode="HTML")

@router.message(AdminStates.adding_promo_material, F.photo, admin_filter)
async def process_new_material(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    
    await update_setting('promo_banner_id', file_id)
    await log_action(message.from_user.id, "update_banner", f"New banner uploaded")
    
    await message.answer("✅ <b>Rasm muvaffaqiyatli o'rnatildi!</b>\n\nBu rasm endi tizimda ishlatiladi.", parse_mode="HTML")
    await state.clear()
    
    from .base import get_admin_main_kb
    from database.db import get_admin
    adm = await get_admin(message.from_user.id)
    perms = adm[2] if adm else 'all'
    await message.answer("<b>💎 PREMIUM ADMIN PANEL</b>\n━━━━━━━━━━━━━━\nBo'limni tanlang:", reply_markup=get_admin_main_kb(message.from_user.id, perms), parse_mode="HTML")

@router.message(AdminStates.adding_promo_material, admin_filter)
async def process_new_material_invalid(message: types.Message):
    await message.answer("❌ Iltimos, faqat rasm (photo) yuboring:")
