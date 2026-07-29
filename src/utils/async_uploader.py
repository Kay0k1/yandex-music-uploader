import os
import asyncio
import urllib.parse
from typing import Optional
from yandex_music import ClientAsync
from yandex_music.utils.request_async import Request
from yandex_music.exceptions import NetworkError
import aiohttp
import logging

logger = logging.getLogger(__name__)

PROXY_URL = os.getenv("YANDEX_PROXY_URL")  # e.g. http://user:pass@host:port

# Сколько раз повторять заливку и сколько ждать между попытками.
UPLOAD_MAX_RETRIES = 3
UPLOAD_RETRY_BASE_DELAY = 2  # секунды, умножается на номер попытки

# Сетевые сбои, которые лечатся повтором. RU-прокси периодически отдаёт
# 502 Bad Gateway (ClientHttpProxyError) на отдельные music-loader хосты —
# без этого повтора одна такая осечка = провал загрузки для пользователя.
_RETRYABLE_EXC = (aiohttp.ClientError, asyncio.TimeoutError, NetworkError)


class _RetryableUploadError(Exception):
    """Временный сбой заливки — имеет смысл повторить с новым upload-target."""

# Внутренние веб-ручки music.yandex.ru отвечают только на запросы, похожие на
# браузерные: без Referer/User-Agent/X-Retpath-Y они отдают 404.
_WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _web_headers(token: str, uid) -> dict:
    return {
        "Authorization": f"OAuth {token}",
        "User-Agent": _WEB_UA,
        "Referer": "https://music.yandex.ru/users/me/tracks",
        "Origin": "https://music.yandex.ru",
        "X-Retpath-Y": "https://music.yandex.ru",
        "X-Current-UID": str(uid),
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }


async def _post_web_handler(session, url: str, headers: dict, *, json=None, data=None,
                            params=None, timeout: int = 30) -> bool:
    """
    Дёргает внутреннюю ручку music.yandex.ru и подробно логирует результат.
    Библиотечный client.request прятал всё под «Unknown HTTPError», из-за чего
    причина сбоя была не видна. Возвращает True при успехе.
    """
    try:
        async with session.post(url, headers=headers, json=json, data=data,
                                params=params, timeout=timeout, proxy=PROXY_URL) as resp:
            body = (await resp.text())[:300]
            if resp.status == 200:
                logger.info(f"Web handler OK: {url.rsplit('/', 1)[-1]}")
                return True
            logger.error(
                f"Web handler FAILED: {url} -> HTTP {resp.status}; body: {body!r}"
            )
            return False
    except Exception as e:
        logger.error(f"Web handler EXCEPTION: {url} -> {type(e).__name__}: {e!r}")
        return False


async def _acquire_target_and_upload(session, url_req: str, headers: dict,
                                     file_path: str, file_name: str, attempt: int) -> Optional[str]:
    """
    Берёт у Яндекса свежий upload-target и заливает в него файл.
    Возвращает ugc-track-id. Временные сбои поднимает как _RetryableUploadError.

    Target выдаётся на конкретный music-loader хост, и сбои обычно привязаны
    именно к хосту (у прокси нет до него живого маршрута). Поэтому повтор
    запрашивает НОВЫЙ target, а не долбится в тот же адрес.
    """
    try:
        async with session.post(url_req, headers=headers, proxy=PROXY_URL) as resp_url:
            text = None
            if resp_url.status != 200:
                text = await resp_url.text()
                # 401/403 — протухший токен, повторять бессмысленно.
                if resp_url.status in (401, 403):
                    raise Exception(
                        f"Failed to get upload URL: HTTP {resp_url.status}. Response: {text}")
                raise _RetryableUploadError(f"upload-url HTTP {resp_url.status}: {text[:200]}")
            data = await resp_url.json()
    except _RetryableUploadError:
        raise
    except _RETRYABLE_EXC as e:
        raise _RetryableUploadError(f"upload-url {type(e).__name__}: {e}") from e

    logger.info(f"Yandex Upload URL Data: {data}")

    upload_url = data.get('post-target') or data.get('post_target')
    track_id = data.get("ugc-track-id") or data.get("ugc_track_id")

    if not upload_url:
        raise Exception(f"No upload URL in response. Data: {data}")

    logger.info(f"Uploading file to: {upload_url}")

    try:
        form = aiohttp.FormData()
        with open(file_path, 'rb') as f:
            form.add_field('file', f, filename=file_name)

            async with session.post(upload_url, data=form, timeout=300, proxy=PROXY_URL) as resp:
                result_text = await resp.text()
                logger.info(f"Upload Result (attempt {attempt}, HTTP {resp.status}): {result_text}")

                if resp.status not in (200, 201):
                    raise _RetryableUploadError(
                        f"upload HTTP {resp.status}: {result_text[:200]}")

                upper_text = result_text.upper()
                if 'OK' not in upper_text and 'CREATED' not in upper_text:
                    raise _RetryableUploadError(
                        f"empty/unexpected upload body: {result_text[:200]!r}")
    except _RetryableUploadError:
        raise
    except _RETRYABLE_EXC as e:
        raise _RetryableUploadError(f"upload {type(e).__name__}: {e}") from e

    return track_id


async def upload_track_async(
    token: str,
    playlist_kind: str,
    file_path: str,
    yandex_filename: Optional[str] = None,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    cover_path: Optional[str] = None,
) -> list[str]:
    """Загружает трек. Возвращает список нефатальных проблем: "name" / "cover"."""
    request = Request(proxy_url=PROXY_URL) if PROXY_URL else None

    # init() тоже ходит через прокси и ловит те же 502 — без повтора загрузка
    # падала бы ещё до запроса upload-url.
    client = None
    for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
        try:
            client = await ClientAsync(token, request=request).init()
            break
        except _RETRYABLE_EXC as e:
            if attempt >= UPLOAD_MAX_RETRIES:
                raise
            delay = UPLOAD_RETRY_BASE_DELAY * attempt
            logger.warning(
                f"Yandex client init attempt {attempt} failed "
                f"({type(e).__name__}: {e}); retrying in {delay}s..."
            )
            await asyncio.sleep(delay)

    uid = client.me.account.uid

    file_name = os.path.basename(file_path)
    encoded = urllib.parse.quote(file_name, safe='_!() ')
    encoded = encoded.replace(' ', '+')

    url_req = f'https://api.music.yandex.net/loader/upload-url?uid={uid}&playlist-id={uid}:{playlist_kind}&visibility=private&path={encoded}'

    logger.info(f"Requesting upload URL: {url_req}")

    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"OAuth {token}"}

        track_id = None
        for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
            try:
                track_id = await _acquire_target_and_upload(
                    session, url_req, headers, file_path, file_name, attempt
                )
                break  # успех
            except _RetryableUploadError as e:
                if attempt >= UPLOAD_MAX_RETRIES:
                    raise Exception(
                        f"Upload failed after {UPLOAD_MAX_RETRIES} attempts. Last error: {e}"
                    ) from e
                delay = UPLOAD_RETRY_BASE_DELAY * attempt
                logger.warning(
                    f"Upload attempt {attempt} failed ({e}); "
                    f"retrying in {delay}s with a fresh upload target..."
                )
                await asyncio.sleep(delay)

    # Шаги ниже — «косметика» поверх уже залитого трека. Если они падают,
    # файл всё равно в плейлисте, поэтому не роняем загрузку, а возвращаем
    # предупреждения наверх, чтобы честно сказать об этом пользователю.
    warnings: list[str] = []

    headers = _web_headers(token, uid)

    async with aiohttp.ClientSession() as web:
        if title and track_id:
            logger.info(f"Renaming track {track_id} to: {artist} - {title}")
            full_title = f"{artist} - {title}" if artist and artist != "Unknown Artist" else title

            ok = await _post_web_handler(
                web,
                "https://music.yandex.ru/api/v2/handlers/edit-track-name",
                headers,
                json={"trackId": track_id, "value": full_title},
                timeout=10,
            )
            if not ok:
                warnings.append("name")

        if cover_path and os.path.exists(cover_path) and track_id:
            logger.info(f"Uploading cover for track {track_id}")
            try:
                with open(cover_path, "rb") as img:
                    file_bytes = img.read()
            except OSError as e:
                logger.error(f"Cannot read cover {cover_path}: {e}")
                file_bytes = None

            if file_bytes:
                form_cover = aiohttp.FormData()
                form_cover.add_field('cover', file_bytes, filename='cover.jpg',
                                     content_type='image/jpeg')

                ok = await _post_web_handler(
                    web,
                    "https://music.yandex.ru/api/v2/handlers/edit-track-cover",
                    headers,
                    data=form_cover,
                    params={"trackId": track_id},
                    timeout=30,
                )
                if not ok:
                    warnings.append("cover")
            else:
                warnings.append("cover")

    return warnings
