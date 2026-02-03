import os
import urllib.parse
from typing import Optional
from yandex_music import ClientAsync
import aiohttp

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
    
    params = {
        'uid': uid,
        'playlist-id': f"{uid}:{playlist_kind}",
        'visibility': 'private',
        'path': "track.mp3", # Упрощаем путь для теста
    }

    # DEBUG: Логируем параметры для Яндекса
    print(f"DEBUG: UID={uid}, PlaylistID={params['playlist-id']}, Path={params['path']}")

    data = await client.request.post(
        url='https://api.music.yandex.net/loader/upload-url',
        params=params,
        timeout=10,
    )
    
    # DEBUG: Логируем полный ответ
    print(f"DEBUG: Yandex Response Data={data}")
    
    if not isinstance(data, dict) or 'post-target' not in data:
        error_msg = data.get('message', 'Unknown error') if isinstance(data, dict) else str(data)
        raise Exception(f"Failed to get upload URL. Response: {error_msg}")

    upload_url = data['post-target']
    track_id = data.get("ugc-track-id")

    form = aiohttp.FormData()

    with open(file_path, 'rb') as f:
        form.add_field('file', f, filename=final_yandex_name)

        resp = await client.request.post(
            url=upload_url,
            data=form,
            timeout=300,
        )
        
        if resp != 'CREATED':
            print(f"Warning: Upload response was {resp}")

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
