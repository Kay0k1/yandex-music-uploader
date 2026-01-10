import os
from typing import Optional, Tuple
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC

def extract_metadata(file_path: str) -> Tuple[str, str, Optional[str]]:
    """
    Возвращает: (artist, title, path_to_cover_image)
    Если тегов нет, возвращает имя файла и Unknown Artist.
    Если обложки нет, path_to_cover_image будет None.
    """
    try:
        audio = MP3(file_path, ID3=ID3)
    except Exception:
        return "Unknown Artist", os.path.basename(file_path), None

    title = str(audio.get("TIT2", os.path.basename(file_path)))
    artist = str(audio.get("TPE1", "Unknown Artist"))

    cover_path = None
    if audio.tags:
        for tag in audio.tags.values():
            if isinstance(tag, APIC):
                cover_filename = file_path + ".jpg"
                with open(cover_filename, "wb") as img:
                    img.write(tag.data)
                cover_path = cover_filename
                break

    return artist, title, cover_path
