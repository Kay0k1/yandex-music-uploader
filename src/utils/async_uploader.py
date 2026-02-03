import os
import urllib.parse
from typing import Optional
from yandex_music import ClientAsync
import aiohttp
import logging

logger = logging.getLogger(__name__)

async def upload_track_async(
    token: str,
    playlist_kind: str,
    file_path: str,
    yandex_filename: Optional[str] = None,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    cover_path: Optional[str] = None,
) -> None:
    client = await ClientAsync(token).init()
    uid = client.me.account.uid
    
    # Используем оригинальное имя файла (без file_id, так как мы теперь в подпапке)
    file_name = os.path.basename(file_path)
    encoded = urllib.parse.quote(file_name, safe='_!() ')
    encoded = encoded.replace(' ', '+')
    
    params = {
        'uid': uid,
        'playlist-id': f"{uid}:{playlist_kind}",
        'visibility': 'private',
        'path': encoded,
    }

    # Получаем URL для загрузки
    data = await client.request.post(
        url='https://api.music.yandex.net/loader/upload-url',
        params=params,
        timeout=10,
    )
    
    # API Яндекса может возвращать разные варианты написания ключей
    upload_url = data.get('post-target') or data.get('post_target')
    track_id = data.get("ugc-track-id") or data.get("ugc_track_id")
    
    if not upload_url:
        error_msg = data.get('message', 'Unknown error') if isinstance(data, dict) else str(data)
        raise Exception(f"Failed to get upload URL. Response API: {error_msg}. Raw: {data}")

    # Важно: загружаем файл через чистый aiohttp, чтобы заголовки библиотеки не мешали
    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        with open(file_path, 'rb') as f:
            form.add_field('file', f, filename=file_name)

            async with session.post(upload_url, data=form, timeout=300) as resp:
                result_text = await resp.text()
                if resp.status != 200 or result_text != 'OK':
                    # В некоторых случаях Яндекс возвращает 'OK' или 'CREATED'
                    # Судя по логам, бывает разное. Проверим результат
                    if result_text not in ('OK', 'CREATED'):
                        raise Exception(f"Upload failed: HTTP {resp.status}. Response: {result_text}")

    if title and track_id:
        full_title = f"{artist} - {title}" if artist and artist != "Unknown Artist" else title
        
        await client.request.post(
            url="https://music.yandex.ru/api/v2/handlers/edit-track-name",
            json={"trackId": track_id, "value": full_title},
            timeout=10,
        )

    if cover_path and os.path.exists(cover_path) and track_id:
        with open(cover_path, "rb") as img:
            file_bytes = img.read()

        form_cover = aiohttp.FormData()
        form_cover.add_field('cover', file_bytes, filename='cover.jpg', content_type='image/jpeg')

        await client.request.post(
            url="https://music.yandex.ru/api/v2/handlers/edit-track-cover",
            params={"trackId": track_id},
            data=form_cover,
            timeout=30,
        )
