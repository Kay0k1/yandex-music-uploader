import os
import html
import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command, BaseFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.database import crud
from src.database.models import async_session
from src.utils.states import BroadcastStates

router = Router()
logger = logging.getLogger(__name__)

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
    builder.button(text="📢 Бродкаст", callback_data="admin_broadcast")
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


# ─── Broadcast ───────────────────────────────────────

@router.callback_query(F.data == "admin_broadcast", AdminFilter())
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastStates.waiting_for_message)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="admin_broadcast_cancel")
    
    await callback.message.edit_text(
        "<b>📢 Бродкаст</b>\n\n"
        "Отправь мне сообщение, которое я разошлю всем пользователям.\n\n"
        "Поддерживается: текст, фото, видео, аудио, документ.\n"
        "Форматирование (жирный, курсив) сохранится.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_broadcast_cancel", AdminFilter())
async def cb_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb_refresh(callback)


@router.message(BroadcastStates.waiting_for_message, AdminFilter())
async def handle_broadcast_message(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    
    async with async_session() as session:
        tg_ids = await crud.get_all_tg_ids(session)

    total = len(tg_ids)
    success = 0
    failed = 0

    status_msg = await message.answer(
        f"📢 <b>Рассылка запущена...</b>\n\n"
        f"👥 Всего: {total}\n"
        f"⏳ Отправлено: 0/{total}",
        parse_mode="HTML"
    )

    for i, tg_id in enumerate(tg_ids):
        try:
            await message.copy_to(tg_id)
            success += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Broadcast failed for {tg_id}: {e}")
        
        # Telegram rate limit: ~30 msg/sec
        if (i + 1) % 25 == 0:
            await asyncio.sleep(1)
            try:
                await status_msg.edit_text(
                    f"📢 <b>Рассылка...</b>\n\n"
                    f"✅ Доставлено: {success}\n"
                    f"❌ Не доставлено: {failed}\n"
                    f"⏳ Прогресс: {i + 1}/{total}",
                    parse_mode="HTML"
                )
            except:
                pass

    await status_msg.edit_text(
        f"📢 <b>Рассылка завершена!</b>\n\n"
        f"✅ Доставлено: <b>{success}</b>\n"
        f"❌ Не доставлено: <b>{failed}</b>\n"
        f"👥 Всего: <b>{total}</b>",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )
