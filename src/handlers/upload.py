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
from src.utils.async_uploader import upload_track_async, UploadAuthError

router = Router()
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
MAX_FILENAME_LEN = 120
# Подпись к фото в Telegram ограничена 1024 символами, остальной текст
# сообщения занимает около 300.
MAX_CAPTION_FIELD_LEN = 200

MP3_MIME_TYPES = {"audio/mpeg", "audio/mp3", "audio/mpeg3", "audio/x-mpeg-3"}

NOT_MP3_TEXT = (
    "🎵 Яндекс.Музыка принимает только MP3.\n"
    "Пришли трек в формате .mp3 — можно как аудио или как файл."
)
UPLOAD_FAILED_TEXT = (
    "❌ Не получилось загрузить трек.\n"
    "Пришли его ещё раз чуть позже — обычно это временный сбой у Яндекса."
)
AUTH_EXPIRED_TEXT = (
    "🔑 Яндекс не принял авторизацию — похоже, она слетела.\n"
    "Авторизуйся заново: /auth, потом /add и пришли трек ещё раз."
)

AD_COVER_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "bot_fallback_cover.png")


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


def is_mp3(mime_type: str | None, file_name: str | None) -> bool:
    if file_name and file_name.lower().endswith(".mp3"):
        return True
    return (mime_type or "").lower() in MP3_MIME_TYPES


def _shorten(text: str, limit: int = MAX_CAPTION_FIELD_LEN) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


def build_result_caption(artist: str, title: str, warnings: list[str]) -> str:
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

    return (
        f"{header}\n\n"
        f"👤 Артист: {html.escape(_shorten(artist))}\n"
        f"🎼 Трек: {html.escape(_shorten(title))}\n"
        f"{note}\n"
        f"кидай еще или тыкай /end для выхода.\n\n"
        f"——————————————\n"
        f"<a href=\"https://t.me/internet_connected_bot?start=ref_AKW7U53A\">Ускоритель интернета</a>"
    )


async def send_upload_result(message: Message, caption: str, cover_path: str | None) -> None:
    """
    Трек к этому моменту уже в Яндексе, поэтому сбой отправки ответа не должен
    выглядеть как провал загрузки: иначе человек перезальёт трек и получит дубль.
    Обложка из тегов бывает битой или неподходящей для Telegram — тогда
    пробуем запасную картинку, а за ней обычный текст.
    """
    for photo_path in (cover_path, AD_COVER_PATH):
        if not photo_path:
            continue
        try:
            await message.answer_photo(FSInputFile(photo_path), caption=caption, parse_mode="HTML")
            return
        except Exception:
            logger.warning(
                "Telegram rejected the %s photo for chat %s",
                "track" if photo_path == cover_path else "fallback", message.chat.id,
                exc_info=True,
            )
    try:
        await message.answer(caption, parse_mode="HTML")
    except Exception:
        logger.exception("Could not deliver upload result to chat %s", message.chat.id)


async def _report_failure(message: Message, status_msg: Message, text: str) -> None:
    try:
        await status_msg.edit_text(text)
        return
    except Exception:
        pass
    try:
        await message.reply(text)
    except Exception:
        logger.warning("Could not deliver error message to chat %s", message.chat.id)


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
        f"Выбран плейлист: <b>{html.escape(playlist.title or 'Без названия')}</b>\n\n"
        f"Кидай мне .mp3 файлы, а я буду их загружать.\n"
        f"Для выхода тыкни /end",
        parse_mode="HTML"
    )

@router.message(Command("end"), UserSteps.uploading)
async def cmd_end_upload(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Вышли из режима загрузки", reply_markup=ReplyKeyboardRemove())


@router.message(Command("end"), StateFilter(None))
async def cmd_end_without_upload_mode(message: Message):
    await message.answer("Режим загрузки и так выключен. Включить: /add")


@router.message(UserSteps.uploading, F.audio | F.document)
async def process_audio_upload(message: Message, state: FSMContext, bot: Bot):
    media = message.audio or message.document
    if not is_mp3(media.mime_type, media.file_name):
        await message.reply(NOT_MP3_TEXT)
        return

    data = await state.get_data()
    tg_id = message.from_user.id
    token = data.get("token")
    playlist_kind = data.get("playlist_kind")

    if media.file_size and media.file_size > MAX_FILE_SIZE:
        await message.reply("❌ Файл слишком большой. Максимальный размер — 2 ГБ.")
        return

    status_msg = await message.reply("⏳ Скачиваю файл...")

    file_id = media.file_id
    file_name = media.file_name or "track.mp3"
    safe_filename = sanitize_filename(file_name)

    file_dir = os.path.join(DOWNLOAD_DIR, file_id)
    os.makedirs(file_dir, exist_ok=True)
    file_path = os.path.join(file_dir, safe_filename)

    cover_path = None
    try:
        try:
            await bot.download(media, destination=file_path)

            await status_msg.edit_text("🎵 Читаю метаданные...")

            artist_fallback = getattr(media, "performer", None) or "Unknown Artist"
            title_fallback = getattr(media, "title", None) or None
            artist, title, cover_path = await asyncio.to_thread(
                extract_metadata, file_path, artist_fallback, title_fallback
            )

            await status_msg.edit_text(
                f"🚀 Загружаю в Яндекс: <b>{html.escape(_shorten(artist))} - {html.escape(_shorten(title))}</b>...",
                parse_mode="HTML",
            )

            warnings = await upload_track_async(
                token=token,
                playlist_kind=playlist_kind,
                file_path=file_path,
                yandex_filename=safe_filename,
                title=title,
                artist=artist,
                cover_path=cover_path
            )
        except UploadAuthError:
            logger.warning("Yandex rejected the token for tg_id=%s", tg_id, exc_info=True)
            await _report_failure(message, status_msg, AUTH_EXPIRED_TEXT)
            return
        except Exception:
            logger.exception("Upload failed for tg_id=%s file=%s", tg_id, safe_filename)
            await _report_failure(message, status_msg, UPLOAD_FAILED_TEXT)
            return

        try:
            async with async_session() as session:
                await crud.add_track(session, tg_id, artist, title)
        except Exception:
            logger.exception("Could not record uploaded track for tg_id=%s", tg_id)

        try:
            await status_msg.delete()
        except Exception:
            pass

        await send_upload_result(message, build_result_caption(artist, title, warnings or []), cover_path)

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


@router.message(StateFilter(None), F.audio | F.document)
async def audio_without_upload_mode(message: Message):
    """
    FSM живёт в памяти и обнуляется при рестарте бота: пользователь, который был
    в режиме загрузки, иначе получил бы молчание в ответ на файл.
    """
    if message.document and not is_mp3(message.document.mime_type, message.document.file_name):
        return
    await message.reply(
        "🎵 Вижу файл, но режим загрузки выключен.\n"
        "Включи его командой /add и пришли трек ещё раз."
    )
