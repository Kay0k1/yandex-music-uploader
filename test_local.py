import sys
from aiogram.client.telegram import TelegramAPIServer

server = TelegramAPIServer.from_base("http://telegram-bot-api:8081", is_local=True)
print(f"Is local: {server.is_local}")
