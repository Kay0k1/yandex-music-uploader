from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message

from src.database import crud
from src.database.models import async_session


class CheckTokenMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        allowed_commands = ['/start', '/help', '/auth']
        
        if event.text:
            command = event.text.split()[0].lower()
            if command in allowed_commands:
                return await handler(event, data)

        tg_id = user.id
        has_token = False

        async with async_session() as session:
            db_user = await crud.get_user(session, tg_id)
            
            if db_user and db_user.token:
                has_token = True

        if has_token:
            return await handler(event, data)
        else:
            await event.answer(
                "⚠️ <b>Доступ запрещен.</b>\n\n"
                "Сначала авторизуйся через /start или /auth",
                parse_mode="HTML"
            )
            return