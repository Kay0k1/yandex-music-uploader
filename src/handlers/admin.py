import os
import html
from aiogram import Router, F
from aiogram.filters import Command, BaseFilter
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.database import crud
from src.database.models import async_session

router = Router()

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
PAGE_SIZE = 10


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id if event.from_user else None
        return user_id in ADMIN_IDS


def get_admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🏆 Топ пользователей", callback_data="admin_top:0")
    builder.button(text="🎵 Последние треки", callback_data="admin_tracks:0")
    builder.button(text="🔄 Обновить стату", callback_data="admin_refresh")
    builder.adjust(1)
    return builder.as_markup()


def get_pagination_keyboard(prefix: str, page: int, has_more: bool):
    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="⬅️ Назад", callback_data=f"{prefix}:{page - 1}")
    if has_more:
        builder.button(text="Вперёд ➡️", callback_data=f"{prefix}:{page + 1}")
    builder.button(text="🔙 В меню", callback_data="admin_refresh")
    builder.adjust(2, 1)
    return builder.as_markup()


@router.message(Command("admin"), AdminFilter())
async def cmd_admin(message: Message):
    async with async_session() as session:
        users_count, tracks_count = await crud.get_global_stats(session)

    text = (
        f"<b>👮‍♂️ Панель администратора</b>\n\n"
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


@router.callback_query(F.data.startswith("admin_top:"), AdminFilter())
async def cb_top_users(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    offset = page * PAGE_SIZE
    
    async with async_session() as session:
        users = await crud.get_top_users(session, limit=PAGE_SIZE + 1, offset=offset)

    if not users and page == 0:
        await callback.answer("Пусто...", show_alert=True)
        return

    has_more = len(users) > PAGE_SIZE
    users = users[:PAGE_SIZE]

    text = f"<b>🏆 Топ пользователей по загрузкам (стр. {page + 1}):</b>\n\n"
    for i, user in enumerate(users, start=offset + 1):
        username = f"@{user.username}" if hasattr(user, 'username') and user.username else f"ID: <code>{user.tg_id}</code>"
        text += f"{i}. {username} — <b>{user.track_count}</b> треков\n"

    await callback.message.edit_text(
        text, 
        reply_markup=get_pagination_keyboard("admin_top", page, has_more), 
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_tracks:"), AdminFilter())
async def cb_last_tracks(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    offset = page * PAGE_SIZE
    
    async with async_session() as session:
        tracks = await crud.get_last_tracks(session, limit=PAGE_SIZE + 1, offset=offset)

    if not tracks and page == 0:
        await callback.answer("Треков пока нет...", show_alert=True)
        return

    has_more = len(tracks) > PAGE_SIZE
    tracks = tracks[:PAGE_SIZE]

    text = f"<b>🎵 Последние загрузки (стр. {page + 1}):</b>\n\n"
    for track in tracks:
        artist = html.escape(track.artist)
        title = html.escape(track.title)
        tg_id = track.user.tg_id if track.user else "?"
        username = getattr(track.user, 'username', None) if track.user else None
        user_display = f"@{username}" if username else f"<code>{tg_id}</code>"
        text += f"💿 <b>{artist} - {title}</b>\n└ {user_display}\n\n"

    await callback.message.edit_text(
        text, 
        reply_markup=get_pagination_keyboard("admin_tracks", page, has_more), 
        parse_mode="HTML"
    )
    await callback.answer()
