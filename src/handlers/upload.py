import os
import html
import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, ReplyKeyboardRemove, FSInputFile
from aiogram.fsm.context import FSMContext

from src.database import crud
from src.database.models import async_session
from src.utils.states import UserSteps
from src.utils.metadata import extract_metadata
from src.utils.async_uploader import upload_track_async

router = Router()
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
MAX_FILENAME_LEN = 120


def sanitize_filename(file_name: str) -> str:
    """Чистит имя файла. Гарантирует непустое имя разумной длины с .mp3 на конце."""
    cleaned = "".join(
        c for c in file_name if c.isalpha() or c.isdigit() or c in (' ', '.', '_')
    ).strip()

    stem = cleaned[:-4] if cleaned.lower().endswith(".mp3") else cleaned

    # имя из одних эмодзи/дефисов схлопывается в пустоту или в дотфайл
    stem = stem.strip(" .")
    if not stem:
        stem = "track"

    return stem[:MAX_FILENAME_LEN] + ".mp3"

AD_COVER_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "bot_fallback_cover.png")

@router.message(Command("add"))
async def cmd_add_track(message: Message, state: FSMContext):
    tg_id = message.from_user.id

    async with async_session() as session:
        token = await crud.get_token(session, tg_id)
        playlist = await crud.get_active_playlist(session, tg_id)

    if not token:
        await message.answer("Сначала авторизуйся через /auth")
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

    if message.audio.file_size and message.audio.file_size > MAX_FILE_SIZE:
        await message.reply("❌ Файл слишком большой. Максимальный размер — 2 ГБ.")
        return

    status_msg = await message.reply("⏳ Скачиваю файл...")

    file_id = message.audio.file_id
    file_name = message.audio.file_name or "track.mp3"
    safe_filename = sanitize_filename(file_name)

    file_dir = os.path.join(DOWNLOAD_DIR, file_id)
    os.makedirs(file_dir, exist_ok=True)
    file_path = os.path.join(file_dir, safe_filename)

    cover_path = None
    try:
        await bot.download(message.audio, destination=file_path)

        await status_msg.edit_text("🎵 Читаю метаданные...")

        artist_fallback = message.audio.performer or "Unknown Artist"
        title_fallback = message.audio.title or None
        artist, title, cover_path = await asyncio.to_thread(
            extract_metadata, file_path, artist_fallback, title_fallback
        )

        await status_msg.edit_text(f"🚀 Загружаю в Яндекс: <b>{html.escape(artist)} - {html.escape(title)}</b>...", parse_mode="HTML")

        warnings = await upload_track_async(
            token=token,
            playlist_kind=playlist_kind,
            file_path=file_path,
            yandex_filename=safe_filename,
            title=title,
            artist=artist,
            cover_path=cover_path
        )

        async with async_session() as session:
            await crud.add_track(session, tg_id, artist, title)

        warnings = warnings or []
        if "name" in warnings:
            note = (
                "\n⚠️ Название в Яндексе выставить не удалось — "
                "трек лежит под именем файла, переименуй вручную.\n"
            )
        else:
            note = ""
        if "cover" in warnings:
            note += "⚠️ Обложку прикрепить не удалось.\n"

        header = "✅ <b>Загружено!</b>" if not warnings else "☑️ <b>Трек загружен, но не всё получилось</b>"

        success_text = (
            f"{header}\n\n"
            f"👤 Артист: {html.escape(artist)}\n"
            f"🎼 Трек: {html.escape(title)}\n"
            f"{note}\n"
            f"кидай еще или тыкай /end для выхода.\n\n"
            f"——————————————\n"
            f"<a href=\"https://t.me/internet_connected_bot?start=ref_AKW7U53A\">Ускоритель интернета</a>"
        )

        await status_msg.delete()
        status_msg = None

        if cover_path:
            photo = FSInputFile(cover_path)
        else:
            photo = FSInputFile(AD_COVER_PATH)
        await message.answer_photo(photo, caption=success_text, parse_mode="HTML")

    except Exception as e:
        logger.exception("Upload failed for tg_id=%s file=%s", tg_id, safe_filename)
        # status_msg уже удалено, если падение случилось на отправке результата
        try:
            if status_msg:
                await status_msg.edit_text(f"❌ Ошибка при загрузке: {e}")
            else:
                await message.reply(f"❌ Ошибка при загрузке: {e}")
        except Exception:
            logger.warning("Could not deliver error message to tg_id=%s", tg_id)

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        if cover_path and os.path.exists(cover_path):
            os.remove(cover_path)

        file_dir = os.path.dirname(file_path)
        if os.path.exists(file_dir) and file_dir != DOWNLOAD_DIR:
            try:
                os.rmdir(file_dir)
            except Exception:
                pass


@router.message(StateFilter(None), F.audio)
async def audio_without_upload_mode(message: Message):
    """
    FSM живёт в памяти и обнуляется при рестарте бота: пользователь, который был
    в режиме загрузки, иначе получил бы молчание в ответ на файл.
    """
    await message.reply(
        "🎵 Вижу файл, но режим загрузки выключен.\n"
        "Включи его командой /add и пришли трек ещё раз."
    )
