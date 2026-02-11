from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData


class PlaylistCallback(CallbackData, prefix="pl"):
    id: int
    action: str

def get_playlists_keyboard(playlists: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for pl in playlists:
        # User requested specific styles encountered in docs/screenshot:
        # success (Green), danger (Red)
        style = "success" if pl.is_active else "danger"
        text = pl.title  # No emojis directly in text
        
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
