import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer, SimpleFilesPathWrapper
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
import pathlib

from src.database.models import async_main

from src.handlers.start import router as start_router

from src.handlers.auth import router as auth_router
from src.handlers.playlist import router as playlist_router
from src.handlers.upload import router as upload_router
from src.handlers.help import router as help_router
from src.handlers.admin import router as admin_router

from src.middlewares.auth_middleware import CheckTokenMiddleware

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.error("Установите BOT_TOKEN")
        sys.exit(1)

    bot_kwargs = {
        "token": bot_token,
        "default": DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True
        )
    }

    server_url = os.getenv("TELEGRAM_API_URL")
    if server_url:
        bot_kwargs["session"] = AiohttpSession(
            api=TelegramAPIServer.from_base(
                server_url,
                is_local=True
            )
        )
        # Because we run inside docker and both containers mount the same volume
        # to `/var/lib/telegram-bot-api`, we can use SimpleFilesPathWrapper.
        # However, looking at telegram-bot-api command from `ps aux`:
        # telegram-bot-api --dir=/var/lib/telegram-bot-api --temp-dir=/tmp/telegram-bot-api
        # It means the server will return paths like `/var/lib/telegram-bot-api/xxx`
        # And our bot container also has `/var/lib/telegram-bot-api/xxx`, so they match perfectly!
        bot_kwargs["session"].api.wrap_local_file = SimpleFilesPathWrapper(
            server_path=pathlib.Path("/var/lib/telegram-bot-api"),
            local_path=pathlib.Path("/var/lib/telegram-bot-api")
        )
        logger.info(f"Используется локальный сервер Telegram API: {server_url}")

    bot = Bot(**bot_kwargs)

    dp = Dispatcher(storage=MemoryStorage())

    dp.message.outer_middleware(CheckTokenMiddleware())

    dp.include_router(start_router)

    dp.include_router(auth_router)
    dp.include_router(playlist_router)
    dp.include_router(upload_router)
    dp.include_router(help_router)
    dp.include_router(admin_router)

    try:
        await async_main()
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        return

    await bot.delete_webhook(drop_pending_updates=True)
    
    logger.info("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:    
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
