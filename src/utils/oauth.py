"""
OAuth 2.0 Device Flow для Yandex Music.

Используем client_id/secret от Smart TV приложения для получения
полных прав на редактирование плейлистов.

Переменные окружения:
    YANDEX_CLIENT_ID     — Client ID приложения Yandex OAuth
    YANDEX_CLIENT_SECRET — Client Secret приложения Yandex OAuth
"""
import os
import aiohttp
import asyncio
import logging
from src.utils.yandex_proxy import (
    PROXY_URL, HTTP_PROXY_URL, PROXY_ERRORS, create_yandex_session,
)

logger = logging.getLogger(__name__)

# Загружаем из переменных окружения; значения по умолчанию — публичные
# credentials Smart TV приложения, используемые в open-source клиентах.
# Настоятельно рекомендуется переопределить через YANDEX_CLIENT_ID/SECRET в .env.
CLIENT_ID = os.getenv('YANDEX_CLIENT_ID', '23cabbbdc6cd418abb4b39c32c41195d')
CLIENT_SECRET = os.getenv('YANDEX_CLIENT_SECRET', '53bc75238f0c4d08a118e51fe9203300')

DEVICE_CODE_URL = 'https://oauth.yandex.ru/device/code'
TOKEN_URL = 'https://oauth.yandex.ru/token'
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=10)
_GATEWAY_ERRORS = (502, 503, 504)

async def _post(session: aiohttp.ClientSession, direct: aiohttp.ClientSession,
                url: str, data: dict):
    """
    POST через RU-прокси (как и остальные вызовы к Яндексу), но с откатом
    на прямое соединение: смерть прокси не должна ронять ещё и авторизацию.
    """
    if PROXY_URL:
        try:
            response = await session.post(
                url, data=data, proxy=HTTP_PROXY_URL, timeout=REQUEST_TIMEOUT)
            if response.status not in _GATEWAY_ERRORS:
                return response
            logger.warning("OAuth: proxy returned HTTP %s, falling back to direct",
                           response.status)
            response.close()
        except (aiohttp.ClientConnectionError, aiohttp.ClientHttpProxyError,
                asyncio.TimeoutError) + PROXY_ERRORS as e:
            logger.warning("OAuth: proxy unavailable (%s), falling back to direct",
                           type(e).__name__)

    return await direct.post(url, data=data, timeout=REQUEST_TIMEOUT)


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
    async with create_yandex_session() as session, aiohttp.ClientSession() as direct:
        data = {
            'client_id': CLIENT_ID,
        }
        async with await _post(session, direct, DEVICE_CODE_URL, data) as resp:
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
    async with create_yandex_session() as session, aiohttp.ClientSession() as direct:
        elapsed = 0
        
        while elapsed < timeout:
            data = {
                'grant_type': 'device_code',
                'code': device_code,
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
            }

            async with await _post(session, direct, TOKEN_URL, data) as resp:
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
