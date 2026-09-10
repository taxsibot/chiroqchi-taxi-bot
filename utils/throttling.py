import time
from typing import Any, Awaitable, Callable, Dict, Union
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 0.3):
        self.limit = limit
        self.caches: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        now = time.time()
        
        if user_id in self.caches:
            if now - self.caches[user_id] < self.limit:
                return None
                
        self.caches[user_id] = now
        return await handler(event, data)
