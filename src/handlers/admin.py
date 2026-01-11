import os
from aiogram import Router, F
from aiogram.filters import Command, BaseFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.database import crud
from src.database.models import async_session

router = Router()

class AdminFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
        return message.from_user.id in admin_ids

def get_admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🏆 Топ пользователей", callback_data="admin_top_users")
    builder.button(text="🎵 Последние треки", callback_data="admin_last_tracks")
    builder.button(text="🔄 Обновить стату", callback_data="admin_refresh")
    builder.adjust(1)
    return builder.as_markup()

@router.message(Command("admin"), AdminFilter())
async def cmd_admin(message: Message):
    async with async_session() as session:
        users_count, tracks_count = await crud.get_global_stats(session)

    text = (
        f"<b>Панель администратора</b>\n\n"
        f"👥 Всего пользователей: <b>{users_count}</b>\n"
        f"💾 Всего загружено треков: <b>{tracks_count}</b>"
    )

    await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_refresh", AdminFilter())
async def cb_refresh(callback: CallbackQuery):
    async with async_session() as session:
        users_count, tracks_count = await crud.get_global_stats(session)

    text = (
        f"<b>👮‍♂️ Панель администратора</b>\n\n"
        f"👥 Всего пользователей: <b>{users_count}</b>\n"
        f"💾 Всего загружено треков: <b>{tracks_count}</b>"
    )

    try:
        await callback.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")
    except:
        pass
    await callback.answer("Обновлено")


@router.callback_query(F.data == "admin_top_users", AdminFilter())
async def cb_top_users(callback: CallbackQuery):
    async with async_session() as session:
        users = await crud.get_top_users(session)

    if not users:
        await callback.answer("Пусто...", show_alert=True)
        return

    text = "<b>🏆 Топ 10 пользователей по загрузкам:</b>\n\n"
    for i, user in enumerate(users, 1):
        text += f"{i}. ID: <code>{user.tg_id}</code> — <b>{user.track_count}</b> треков\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="admin_refresh")
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "admin_last_tracks", AdminFilter())
async def cb_last_tracks(callback: CallbackQuery):
    async with async_session() as session:
        tracks = await crud.get_last_tracks(session)

    if not tracks:
        await callback.answer("Треков пока нет...", show_alert=True)
        return

    text = "<b>🎵 Последние 10 загрузок:</b>\n\n"
    for track in tracks:
        text += f"💿 <b>{track.artist} - {track.title}</b>\n└ Юзер ID: <code>{track.user_id}</code>\n\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="admin_refresh")

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
