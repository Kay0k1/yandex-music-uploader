from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from yandex_music import ClientAsync

from src.database import crud
from src.database.models import async_session
from src.utils.texts import set_active_playlist
from src.utils.keyboards import get_playlists_keyboard, PlaylistCallback

router = Router()

@router.message(Command("set_playlist"))
async def cmd_set_playlist(message: Message, state: FSMContext):
    tg_id = message.from_user.id

    async with async_session() as session:
        token = await crud.get_token(session, tg_id)

    if not token:
        await message.answer("Сначала установи токен через /set_token")
        return

    wait_message = await message.answer("⏳ Подключаюсь к Яндексу и получаю список плейлистов...")

    try:
        client = await ClientAsync(token).init()
        yandex_playlists = await client.users_playlists_list()
        
        if not yandex_playlists:
            await wait_message.edit_text("У тебя нет плейлистов в Яндекс Музыке :(")
            return

        async with async_session() as session:
            await crud.sync_playlists(session, tg_id, yandex_playlists)

            playlists_objects = await crud.get_user_playlists(session, tg_id)

        await wait_message.edit_text(
            text=set_active_playlist,
            reply_markup=get_playlists_keyboard(playlists_objects)
        )

    except Exception as e:
        await wait_message.edit_text(f"Произошла ошибка при получении данных от Яндекса: {e}")


@router.callback_query(PlaylistCallback.filter(F.action == "select"))
async def process_playlist_selection(callback: CallbackQuery, callback_data: PlaylistCallback):
    playlist_id = callback_data.id
    tg_id = callback.from_user.id

    async with async_session() as session:
        await crud.set_active_playlist(session, tg_id, playlist_id)

        playlists_objects = await crud.get_user_playlists(session, tg_id)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=get_playlists_keyboard(playlists_objects)
        )
    except Exception:
        pass

    await callback.answer("Плейлист выбран!")
