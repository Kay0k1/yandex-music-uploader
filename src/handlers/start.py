from aiogram import Router, F
from aiogram.types import Message

from src.utils.texts import main_menu_text

from src.database import crud
from src.database.models import async_session

router = Router()

@router.message(F.text == "/start")
async def cmdstart(message: Message):
    tg_id = message.from_user.id

    async with async_session() as session:
        await crud.create_user(session, tg_id)

    await message.answer(
        main_menu_text,
        parse_mode="HTML"
    )
