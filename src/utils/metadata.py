import os
from typing import Optional, Tuple
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC

def extract_metadata(file_path: str, default_artist: str = "Unknown Artist", default_title: Optional[str] = None) -> Tuple[str, str, Optional[str]]:
    """
    Возвращает: (artist, title, path_to_cover_image)
    Если тегов нет, возвращает переданные дефолты или имя файла.
    Если обложки нет, path_to_cover_image будет None.
    """
    filename = os.path.basename(file_path)
    # Используем уникальный разделитель __SEP__, чтобы точно отделить file_id от имени файла
    if "__SEP__" in filename:
        cleaned_filename = filename.split("__SEP__", 1)[1]
    else:
        cleaned_filename = filename

    try:
        audio = MP3(file_path, ID3=ID3)
    except Exception:
        return default_artist, default_title or cleaned_filename, None

    title = str(audio.get("TIT2", default_title or cleaned_filename))
    artist = str(audio.get("TPE1", default_artist))

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
