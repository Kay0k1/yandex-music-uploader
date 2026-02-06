"""
OAuth 2.0 Device Flow для Yandex Music.

Используем client_id/secret от Smart TV приложения для получения
полных прав на редактирование плейлистов.
"""
import aiohttp
import asyncio
import logging

logger = logging.getLogger(__name__)

CLIENT_ID = '23cabbbdc6cd418abb4b39c32c41195d'
CLIENT_SECRET = '53bc75238f0c4d08a118e51fe9203300'

DEVICE_CODE_URL = 'https://oauth.yandex.ru/device/code'
TOKEN_URL = 'https://oauth.yandex.ru/token'


async def request_device_code() -> dict:
    """
    Запрашивает device_code и user_code для авторизации.
    
    Returns:
        dict: {
            'device_code': str,
            'user_code': str,
            'verification_url': str,
            'expires_in': int,
            'interval': int
        }
    """
    async with aiohttp.ClientSession() as session:
        data = {
            'client_id': CLIENT_ID,
        }
        async with session.post(DEVICE_CODE_URL, data=data) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Failed to get device code: {text}")
            return await resp.json()


async def poll_for_token(device_code: str, interval: int = 5, timeout: int = 300) -> str | None:
    """
    Поллит Yandex OAuth API до получения токена или истечения времени.
    
    Args:
        device_code: Код устройства из request_device_code()
        interval: Интервал между запросами в секундах
        timeout: Максимальное время ожидания в секундах
    
    Returns:
        str: access_token при успехе, None при таймауте
    """
    async with aiohttp.ClientSession() as session:
        elapsed = 0
        
        while elapsed < timeout:
            data = {
                'grant_type': 'device_code',
                'code': device_code,
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
            }

            async with session.post(TOKEN_URL, data=data) as resp:
                result = await resp.json()

                if resp.status == 200 and 'access_token' in result:
                    logger.info("OAuth: Token received successfully")
                    return result['access_token']

                error = result.get('error', '')

                if error == 'authorization_pending':

                    pass
                elif error == 'slow_down':

                    interval += 1
                elif error in ('expired_token', 'access_denied'):

                    logger.warning(f"OAuth: {error}")
                    return None
                else:
                    logger.error(f"OAuth unexpected error: {result}")

            await asyncio.sleep(interval)
            elapsed += interval

        logger.warning("OAuth: Polling timeout")
        return None
