from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from src.utils.texts import help_text

router = Router()

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(help_text)