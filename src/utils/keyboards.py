from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData


class PlaylistCallback(CallbackData, prefix="pl"):
    id: int
    action: str

def get_playlists_keyboard(playlists: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for pl in playlists:
        # Green (positive) for active, Red (destructive) for others
        style = "positive" if pl.is_active else "destructive"
        text = f"{pl.title}" if pl.is_active else pl.title
        
        builder.button(
            text=text,
            callback_data=PlaylistCallback(id=pl.id, action="select"),
            style=style
        )

    builder.adjust(1)

    # Add Main Menu button (Blue/Primary)
    builder.row(
        InlineKeyboardButton(
            text="Главное меню",
            callback_data="main_menu",
            style="primary"
        )
    )

    return builder.as_markup()
