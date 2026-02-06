"""
OAuth Device Flow обработчик для авторизации в Yandex Music.
"""
import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from src.utils.oauth import request_device_code, poll_for_token
from src.utils.texts import auth_prompt, auth_polling, auth_success, auth_expired, auth_already
from src.database import crud
from src.database.models import async_session

router = Router()


@router.message(Command("auth"))
async def cmd_auth(message: Message):
    """Команда /auth для авторизации или переавторизации."""
    tg_id = message.from_user.id
    
    async with async_session() as session:
        await crud.create_user(session, tg_id, message.from_user.username)
    
    await _start_auth_flow(message, tg_id, is_callback=False)


@router.callback_query(F.data == "auth_start")
async def cb_auth_start(callback: CallbackQuery):
    """Начинаем процесс авторизации через Device Flow (кнопка)."""
    await callback.answer()
    
    tg_id = callback.from_user.id
    
    # Проверяем, может уже есть токен (только для кнопки из /start)
    async with async_session() as session:
        existing_token = await crud.get_token(session, tg_id)
        if existing_token:
            await callback.message.edit_text(auth_already, parse_mode="HTML")
            return
    
    await _start_auth_flow(callback.message, tg_id, is_callback=True)


async def _start_auth_flow(message: Message, tg_id: int, is_callback: bool = False):
    """Общий флоу авторизации для команды и callback."""
    try:
        device_data = await request_device_code()
        
        device_code = device_data['device_code']
        user_code = device_data['user_code']
        verification_url = device_data.get('verification_url', 'https://oauth.yandex.ru/device')
        interval = device_data.get('interval', 5)
        expires_in = device_data.get('expires_in', 300)
        
        text = auth_prompt.format(
            url=verification_url,
            code=user_code
        )
        
        if is_callback:
            msg = await message.edit_text(text, parse_mode="HTML")
        else:
            msg = await message.answer(text, parse_mode="HTML")
        
        asyncio.create_task(
            _poll_and_save_token(msg, tg_id, device_code, interval, expires_in)
        )
        
    except Exception as e:
        if is_callback:
            await message.edit_text(f"❌ Ошибка: {e}")
        else:
            await message.answer(f"❌ Ошибка: {e}")


async def _poll_and_save_token(msg: Message, tg_id: int, device_code: str, interval: int, timeout: int):
    """Фоновая задача: поллит токен и сохраняет в БД."""
    
    # Обновляем сообщение
    try:
        await msg.edit_text(msg.text + f"\n\n{auth_polling}", parse_mode="HTML")
    except:
        pass
    
    # Поллим токен
    token = await poll_for_token(device_code, interval=interval, timeout=timeout)
    
    if token:
        # Сохраняем токен
        async with async_session() as session:
            await crud.set_token(session, tg_id, token)
        
        try:
            await msg.edit_text(auth_success, parse_mode="HTML")
        except:
            pass
    else:
        try:
            await msg.edit_text(auth_expired, parse_mode="HTML")
        except:
            pass


def get_auth_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с кнопкой авторизации."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 Авторизоваться", callback_data="auth_start")]
    ])
