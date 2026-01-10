import os
import urllib.parse
from typing import Optional
from yandex_music import ClientAsync
import aiohttp

async def upload_track_async(
    token: str,
    playlist_kind: str,
    file_path: str,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    cover_path: Optional[str] = None,
) -> None:
    client = await ClientAsync(token).init()
    
    file_name = os.path.basename(file_path)
    encoded = urllib.parse.quote(file_name, safe='_!() ')
    encoded = encoded.replace(' ', '+')

    params = {
        'filename': encoded,
        'kind': playlist_kind,
        'visibility': 'private',
        'lang': 'ru',
        'external-domain': 'music.yandex.ru',
        'overembed': 'false',
    }

    data = await client.request.get(
        url='https://music.yandex.ru/handlers/ugc-upload.jsx',
        params=params,
        timeout=10,
    )
    
    upload_url = data['post_target'].replace(':443', '', 1)
    track_id = data.get("track_id")

    form = aiohttp.FormData()

    with open(file_path, 'rb') as f:
        form.add_field('file', f, filename=file_name)

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
