from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData


class PlaylistCallback(CallbackData, prefix="pl"):
    id: int
    action: str

def get_playlists_keyboard(playlists: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for pl in playlists:
        # У плейлиста из Яндекса название может быть пустым, а Telegram
        # не принимает кнопку без текста. Активный помечаем галочкой —
        # поля style в Bot API нет, оно молча игнорировалось.
        title = pl.title or "Без названия"
        text = f"✅ {title}" if pl.is_active else title

        builder.button(
            text=text,
            callback_data=PlaylistCallback(id=pl.id, action="select"),
        )

    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="Главное меню",
            callback_data="main_menu",
        )
    )

    return builder.as_markup()
