import os
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove, FSInputFile
from aiogram.fsm.context import FSMContext

from src.database import crud
from src.database.models import async_session
from src.utils.states import UserSteps
from src.utils.metadata import extract_metadata
from src.utils.async_uploader import upload_track_async

router = Router()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@router.message(Command("add"))
async def cmd_add_track(message: Message, state: FSMContext):
    tg_id = message.from_user.id

    async with async_session() as session:
        token = await crud.get_token(session, tg_id)
        playlist = await crud.get_active_playlist(session, tg_id)

    if not token:
        await message.answer("Сначала установи токен: /set_token")
        return
    
    if not playlist:
        await message.answer("Сначала выбери плейлист: /set_playlist")
        return

    await state.set_state(UserSteps.uploading)
    await state.update_data(token=token, playlist_kind=playlist.kind)

    await message.answer(
        f"📂 <b>Режим загрузки включен!</b>\n"
        f"Выбран плейлист: <b>{playlist.title}</b>\n\n"
        f"Кидай мне .mp3 файлы, а я буду их загружать.\n"
        f"Для выхода тыкни /end",
        parse_mode="HTML"
    )

@router.message(Command("end"), UserSteps.uploading)
async def cmd_end_upload(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Вышли из режима загрузки", reply_markup=ReplyKeyboardRemove())


@router.message(UserSteps.uploading, F.audio)
async def process_audio_upload(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    tg_id = message.from_user.id
    token = data.get("token")
    playlist_kind = data.get("playlist_kind")

    status_msg = await message.reply("⏳ Скачиваю файл...")

    file_id = message.audio.file_id
    file_name = message.audio.file_name or "track.mp3"
    safe_filename = "".join([c for c in file_name if c.isalpha() or c.isdigit() or c in (' ', '.', '_')]).rstrip()
    
    file_path = os.path.join(DOWNLOAD_DIR, f"{file_id}_{safe_filename}")

    try:
        await bot.download(message.audio, destination=file_path)

        await status_msg.edit_text("🎵 Читаю метаданные...")

        artist, title, cover_path = extract_metadata(file_path)

        await status_msg.edit_text(f"🚀 Загружаю в Яндекс: <b>{artist} - {title}</b>...", parse_mode="HTML")

        await upload_track_async(
            token=token,
            playlist_kind=playlist_kind,
            file_path=file_path,
            title=title,
            artist=artist,
            cover_path=cover_path
        )
        
        async with async_session() as session:
            await crud.add_track(session, tg_id, artist, title)

        success_text = f"✅ <b>Загружено!</b>\n\n👤 Артист: {artist}\n🎼 Трек: {title}\n\n кидай еще или тыкай /end для выхода."
        
        await status_msg.delete()

        if cover_path:
            photo = FSInputFile(cover_path)
            await message.answer_photo(photo, caption=success_text, parse_mode="HTML")
        else:
            await message.answer(success_text, parse_mode="HTML")

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка при загрузке: {e}")
        print(f"Upload error: {e}")

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        if cover_path and os.path.exists(cover_path):
            os.remove(cover_path)
