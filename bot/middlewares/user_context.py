# bot/middlewares/user_context.py
from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable

class UserContextMiddleware(BaseMiddleware):
    def __init__(self, memory_repo):
        super().__init__()
        self.memory = memory_repo

    async def __call__(self,
                       handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
                       event: Any,
                       data: Dict[str, Any]) -> Any:
        # Регистрация/обновление пользователя
        m = getattr(event, "from_user", None) or data.get("event_from_user")
        if m:
            await self.memory.ensure_user(
                tg_user_id=m.id,
                username=m.username,
                first=m.first_name,
                last=m.last_name,
                locale=getattr(m, "language_code", None),
            )
            data["tg_user_id"] = m.id
        return await handler(event, data)
