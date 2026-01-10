from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData


class PlaylistCallback(CallbackData, prefix="pl"):
    id: int
    action: str

def get_playlists_keyboard(playlists: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for pl in playlists:
        text = f"✅ {pl.title}" if pl.is_active else pl.title
        
        builder.button(
            text=text,
            callback_data=PlaylistCallback(id=pl.id, action="select")
        )

    builder.adjust(1)
    return builder.as_markup()
