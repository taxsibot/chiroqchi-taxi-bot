from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Any, Awaitable, Union
from database.db import get_user_language

class LanguageMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: dict[str, Any]
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            
        if user:
            # get_user_language is already cached in db.py
            lang = await get_user_language(user.id)
            data['lang'] = lang
        else:
            data['lang'] = 'uz'
            
        return await handler(event, data)
