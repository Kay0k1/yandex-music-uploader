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
    cleaned_filename = filename
    if "_" in filename:
        split_idx = -1
        for i in range(min(80, len(filename)), len(filename)):
            if filename[i] == "_":
                split_idx = i
                break
        
        if split_idx != -1:
            cleaned_filename = filename[split_idx + 1:]
        else:
            last_idx = filename.rfind("_")
            if last_idx > 70:
                cleaned_filename = filename[last_idx + 1:]

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
