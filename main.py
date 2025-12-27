import logging
import os
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from database.models import async_main

from src.handlers.start import router as start_router
from src.handlers.token import router as token_router

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN environment variable")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

dp.include_router(start_router)
dp.include_router(token_router)

async def main():
    await async_main()
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exit") 
