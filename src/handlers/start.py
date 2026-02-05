from aiogram import Router, F
from aiogram.types import Message

from src.utils.texts import welcome_no_auth, welcome_with_auth
from src.handlers.auth import get_auth_keyboard

from src.database import crud
from src.database.models import async_session

router = Router()

@router.message(F.text == "/start")
async def cmdstart(message: Message):
    tg_id = message.from_user.id

    async with async_session() as session:
        await crud.create_user(session, tg_id)
        token = await crud.get_token(session, tg_id)

    if token:
        # Пользователь уже авторизован
        await message.answer(
            welcome_with_auth,
            parse_mode="HTML"
        )
    else:
        # Нужна авторизация
        await message.answer(
            welcome_no_auth,
            parse_mode="HTML",
            reply_markup=get_auth_keyboard()
        )
