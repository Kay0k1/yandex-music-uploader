import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from yandex_music import ClientAsync
from src.utils.yandex_proxy import YandexRequest as Request, PROXY_URL

from src.database import crud
from src.database.models import async_session
from src.utils.texts import set_active_playlist, welcome_with_auth, welcome_no_auth
from src.utils.keyboards import get_playlists_keyboard, PlaylistCallback
from src.utils.states import UserSteps
from src.handlers.auth import get_auth_keyboard

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("set_playlist"))
async def cmd_set_playlist(message: Message, state: FSMContext):
    tg_id = message.from_user.id

    async with async_session() as session:
        token = await crud.get_token(session, tg_id)

    if not token:
        await message.answer("Сначала авторизуйся через /auth")
        return

    wait_message = await message.answer("⏳ Подключаюсь к Яндексу и получаю список плейлистов...")

    try:
        request = Request(proxy_url=PROXY_URL) if PROXY_URL else None
        client = await ClientAsync(token, request=request).init()
        yandex_playlists = await client.users_playlists_list()
        
        if not yandex_playlists:
            # Создаём плейлист "Загрузки" автоматически
            await wait_message.edit_text("📁 Плейлистов нет, создаю «Загрузки»...")
            new_playlist = await client.users_playlists_create("Загрузки", visibility="private")
            
            async with async_session() as session:
                await crud.sync_playlists(session, tg_id, [])
                await crud.create_playlist_and_set_active(session, tg_id, str(new_playlist.kind), new_playlist.title)
            
            await wait_message.edit_text(f"✅ Создан плейлист «{new_playlist.title}»! Он уже выбран. Можешь загружать треки через /add")
            return

        async with async_session() as session:
            await crud.sync_playlists(session, tg_id, yandex_playlists)

            playlists_objects = await crud.get_user_playlists(session, tg_id)

        await wait_message.edit_text(
            text=set_active_playlist,
            reply_markup=get_playlists_keyboard(playlists_objects)
        )

    except Exception:
        logger.exception("Failed to fetch playlists for tg_id=%s", tg_id)
        await wait_message.edit_text(
            "❌ Не удалось получить плейлисты от Яндекса. "
            "Попробуй ещё раз через минуту, а если не поможет — переавторизуйся: /auth"
        )


@router.callback_query(PlaylistCallback.filter(F.action == "select"))
async def process_playlist_selection(callback: CallbackQuery, callback_data: PlaylistCallback,
                                     state: FSMContext):
    playlist_id = callback_data.id
    tg_id = callback.from_user.id

    async with async_session() as session:
        selected = await crud.set_active_playlist(session, tg_id, playlist_id)

        playlists_objects = await crud.get_user_playlists(session, tg_id)

    if selected is None:
        await callback.answer(
            "Этого плейлиста уже нет. Обнови список: /set_playlist", show_alert=True
        )
        return

    # В режиме загрузки плейлист запомнен в состоянии — без этого треки
    # продолжали бы уходить в прежний.
    if await state.get_state() == UserSteps.uploading.state:
        await state.update_data(playlist_kind=selected.kind)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=get_playlists_keyboard(playlists_objects)
        )
    except Exception:
        pass

    await callback.answer("Плейлист выбран!")


@router.callback_query(F.data == "main_menu")
async def process_main_menu(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    tg_id = callback.from_user.id

    async with async_session() as session:
        token = await crud.get_token(session, tg_id)

    if token:
        await callback.message.answer(
            welcome_with_auth,
            parse_mode="HTML"
        )
    else:
        await callback.message.answer(
            welcome_no_auth,
            parse_mode="HTML",
            reply_markup=get_auth_keyboard()
        )
