import re
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from src.utils.states import UserSteps
from src.utils.texts import set_token_text, wrong_token
from src.database import crud
from src. database.models import async_session

router = Router()

TOKEN_PATTERN = re.compile(r'^y0_[a-zA-Z0-9\-_]{30,100}$')

@router.message(Command("set_token"))
async def cmd_set_token(message: Message, state: FSMContext):
    await state.set_state(UserSteps.waiting_for_token)

    await message.answer(
        set_token_text + "\n\n(Для отмены введи /cancel)",
        parse_mode="HTML"
    )

@router.message(Command("cancel"), StateFilter("*"))
@router.message(F.text.casefold() == "отмена", StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await message.answer(
        "Действие отменено.", 
        reply_markup=ReplyKeyboardRemove()
    )


@router.message(UserSteps.waiting_for_token)
async def process_token_input(message: Message, state: FSMContext):
    token = message.text.strip()
    
    if not TOKEN_PATTERN.match(token):
        await message.answer(
            text=wrong_token
        )
        return

    tg_id = message.from_user.id

    if len(token) < 10: 
        await message.answer("Это не похоже на токен. Попробуй еще раз или жми /cancel")
        return

    async with async_session() as session:
        await crud.set_token(session, tg_id, token)

    await state.clear()
    
    await message.answer("Токен успешно сохранен! Теперь можешь отправлять треки.")
