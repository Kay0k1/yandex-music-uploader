"""
OAuth Device Flow обработчик для авторизации в Yandex Music.
"""
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from src.utils.oauth import request_device_code, poll_for_token
from src.utils.texts import auth_prompt, auth_polling, auth_success, auth_expired, auth_already
from src.database import crud
from src.database.models import async_session

router = Router()


@router.callback_query(F.data == "auth_start")
async def cb_auth_start(callback: CallbackQuery):
    """Начинаем процесс авторизации через Device Flow."""
    await callback.answer()
    
    tg_id = callback.from_user.id
    
    # Проверяем, может уже есть токен
    async with async_session() as session:
        existing_token = await crud.get_token(session, tg_id)
        if existing_token:
            await callback.message.edit_text(auth_already, parse_mode="HTML")
            return
    
    try:
        # Запрашиваем device code
        device_data = await request_device_code()
        
        device_code = device_data['device_code']
        user_code = device_data['user_code']
        verification_url = device_data.get('verification_url', 'https://oauth.yandex.ru/device')
        interval = device_data.get('interval', 5)
        expires_in = device_data.get('expires_in', 300)
        
        # Показываем пользователю код и ссылку
        text = auth_prompt.format(
            url=verification_url,
            code=user_code
        )
        
        msg = await callback.message.edit_text(text, parse_mode="HTML")
        
        # Запускаем поллинг в фоне
        asyncio.create_task(
            _poll_and_save_token(msg, tg_id, device_code, interval, expires_in)
        )
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")


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
