import os
import asyncio
import urllib.parse
from typing import Optional
from yandex_music import ClientAsync
from yandex_music.utils.request_async import Request
import aiohttp
import logging

logger = logging.getLogger(__name__)

PROXY_URL = os.getenv("YANDEX_PROXY_URL")  # e.g. http://user:pass@host:port

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
    client = await ClientAsync(token, request=request).init()
    uid = client.me.account.uid

    file_name = os.path.basename(file_path)
    encoded = urllib.parse.quote(file_name, safe='_!() ')
    encoded = encoded.replace(' ', '+')

    url_req = f'https://api.music.yandex.net/loader/upload-url?uid={uid}&playlist-id={uid}:{playlist_kind}&visibility=private&path={encoded}'

    logger.info(f"Requesting upload URL: {url_req}")

    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"OAuth {token}"}
        async with session.post(url_req, headers=headers, proxy=PROXY_URL) as resp_url:
            if resp_url.status != 200:
                text = await resp_url.text()
                raise Exception(f"Failed to get upload URL: HTTP {resp_url.status}. Response: {text}")
            data = await resp_url.json()

        logger.info(f"Yandex Upload URL Data: {data}")

        upload_url = data.get('post-target') or data.get('post_target')
        track_id = data.get("ugc-track-id") or data.get("ugc_track_id")

        if not upload_url:
            raise Exception(f"No upload URL in response. Data: {data}")

        logger.info(f"Uploading file to: {upload_url}")

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            form = aiohttp.FormData()
            with open(file_path, 'rb') as f:
                form.add_field('file', f, filename=file_name)

                async with session.post(upload_url, data=form, timeout=300, proxy=PROXY_URL) as resp:
                    result_text = await resp.text()
                    logger.info(f"Upload Result (attempt {attempt}, HTTP {resp.status}): {result_text}")

                    if resp.status not in (200, 201):
                        raise Exception(f"Upload failed: HTTP {resp.status}. Response: {result_text}")

                    upper_text = result_text.upper()
                    if 'OK' in upper_text or 'CREATED' in upper_text:
                        break  # успех
                    elif attempt < max_retries:
                        logger.warning(f"Upload attempt {attempt} got empty/unexpected body, retrying in 2s...")
                        await asyncio.sleep(2)
                    else:
                        raise Exception(f"Upload failed after {max_retries} attempts. Last body: {result_text}")

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
