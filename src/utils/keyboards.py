from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData


class PlaylistCallback(CallbackData, prefix="pl"):
    id: int
    action: str

def get_playlists_keyboard(playlists: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for pl in playlists:
        style = "success" if pl.is_active else "danger"
        text = pl.title
        
        builder.button(
            text=text,
            callback_data=PlaylistCallback(id=pl.id, action="select"),
            style=style
        )

    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="Главное меню",
            callback_data="main_menu",
            style="primary"
        )
    )

    return builder.as_markup()
