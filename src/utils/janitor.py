"""
Уборка временных файлов локального Telegram Bot API.

Локальный сервер telegram-bot-api складывает каждый скачанный файл в свой том
и НЕ удаляет его сам — том растёт, пока не кончится диск (уже приводило к
падению бота). Бот монтирует тот же том, поэтому подчищаем оттуда сами.

ВНИМАНИЕ: путь до файлов содержит BOT_TOKEN — не логируем пути целиком.
"""
import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

TELEGRAM_DATA_DIR = "/var/lib/telegram-bot-api"
MAX_AGE_SECONDS = 6 * 60 * 60      # файлы старше 6 часов уже не нужны
SWEEP_INTERVAL = 60 * 60           # раз в час
_KEEP_SUFFIXES = (".binlog",)      # состояние самого сервера — не трогаем


def _sweep_once(max_age: int = MAX_AGE_SECONDS) -> tuple[int, int]:
    """Удаляет старые файлы. Возвращает (сколько удалено, сколько байт освобождено)."""
    if not os.path.isdir(TELEGRAM_DATA_DIR):
        return 0, 0

    removed = freed = 0
    cutoff = time.time() - max_age

    for root, dirs, files in os.walk(TELEGRAM_DATA_DIR, topdown=False):
        for name in files:
            if name.endswith(_KEEP_SUFFIXES):
                continue
            path = os.path.join(root, name)
            try:
                st = os.stat(path)
                if st.st_mtime < cutoff:
                    os.remove(path)
                    removed += 1
                    freed += st.st_size
            except OSError:
                continue

        # Подчищаем опустевшие подкаталоги. Корень тома и каталоги первого
        # уровня (по одному на бота) оставляем — их создаёт сам сервер.
        if os.path.dirname(root) not in (TELEGRAM_DATA_DIR, ""):
            try:
                os.rmdir(root)
            except OSError:
                pass

    return removed, freed


async def periodic_cleanup(interval: int = SWEEP_INTERVAL) -> None:
    """Фоновая задача: чистит том раз в час."""
    while True:
        try:
            removed, freed = await asyncio.to_thread(_sweep_once)
            if removed:
                logger.info(
                    "Telegram data cleanup: removed %d file(s), freed %.1f MB",
                    removed, freed / 1024 / 1024,
                )
        except Exception:
            logger.exception("Telegram data cleanup failed")

        await asyncio.sleep(interval)
