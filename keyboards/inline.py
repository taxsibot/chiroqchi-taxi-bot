from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.locales import get_trans

def get_profile_inline_keyboard(role: str, lang: str = 'uz'):
    buttons = [
        [InlineKeyboardButton(text=get_trans(lang, 'edit_name'), callback_data="edit_name"),
         InlineKeyboardButton(text=get_trans(lang, 'edit_phone'), callback_data="edit_phone")],
        [InlineKeyboardButton(text=get_trans(lang, 'edit_lang'), callback_data="edit_language"),
         InlineKeyboardButton(text=get_trans(lang, 'back'), callback_data="close_profile")],
    ]
    
    if role == 'driver':
        buttons.insert(1, [InlineKeyboardButton(text=get_trans(lang, 'edit_car'), callback_data="edit_car")])
        
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_edit_cancel_keyboard(lang: str = 'uz'):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_trans(lang, 'cancel'), callback_data="cancel_edit")]
    ])

def get_skip_secondary_keyboard(lang: str = 'uz'):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_trans(lang, 'skip'), callback_data="skip_secondary")]
    ])
