from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

router = Router()

@router.message(F.text == "/start")
async def cmdstart(message: Message):
    user = message.from_user.id
