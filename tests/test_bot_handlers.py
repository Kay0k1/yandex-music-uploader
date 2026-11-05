import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")

from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

import main
from src.database import crud
from src.handlers import playlist as playlist_handlers
from src.handlers import upload
from src.utils.states import UserSteps


class _Session:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


def _message():
    return SimpleNamespace(
        chat=SimpleNamespace(id=1),
        answer_photo=AsyncMock(),
        answer=AsyncMock(),
        reply=AsyncMock(),
    )


class Mp3DetectionTests(unittest.TestCase):
    def test_mp3_by_mime_or_extension(self):
        self.assertTrue(upload.is_mp3("audio/mpeg", "song.mp3"))
        self.assertTrue(upload.is_mp3("audio/mpeg", None))
        self.assertTrue(upload.is_mp3("application/octet-stream", "Song.MP3"))
        self.assertTrue(upload.is_mp3(None, "song.mp3"))

    def test_other_formats_are_rejected(self):
        self.assertFalse(upload.is_mp3("audio/flac", "song.flac"))
        self.assertFalse(upload.is_mp3("audio/mp4", "song.m4a"))
        self.assertFalse(upload.is_mp3("audio/ogg", None))
        self.assertFalse(upload.is_mp3(None, None))


class ResultCaptionTests(unittest.TestCase):
    def test_long_tags_fit_telegram_caption_limit(self):
        caption = upload.build_result_caption("A" * 5000, "T" * 5000, ["name", "cover"])
        self.assertLessEqual(len(caption), 1024)

    def test_tags_are_html_escaped(self):
        caption = upload.build_result_caption("<b>", "a & b", [])
        self.assertIn("&lt;b&gt;", caption)
        self.assertIn("a &amp; b", caption)


class SendResultTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_track_cover_falls_back_to_bot_cover(self):
        message = _message()
        message.answer_photo.side_effect = [Exception("PHOTO_INVALID_DIMENSIONS"), None]
        await upload.send_upload_result(message, "caption", "/tmp/cover.jpg")
        self.assertEqual(message.answer_photo.await_count, 2)
        message.answer.assert_not_awaited()

    async def test_text_is_sent_when_no_photo_is_accepted(self):
        message = _message()
        message.answer_photo.side_effect = Exception("caption too long")
        await upload.send_upload_result(message, "caption", None)
        message.answer_photo.assert_awaited_once()
        message.answer.assert_awaited_once()

    async def test_failed_delivery_does_not_raise(self):
        message = _message()
        message.answer_photo.side_effect = Exception("blocked")
        message.answer.side_effect = Exception("blocked")
        await upload.send_upload_result(message, "caption", None)


class ReportFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_when_status_message_is_gone(self):
        message = _message()
        status = SimpleNamespace(edit_text=AsyncMock(side_effect=Exception("message to edit not found")))
        await upload._report_failure(message, status, "text")
        message.reply.assert_awaited_once_with("text")


class SyncPlaylistsTests(unittest.IsolatedAsyncioTestCase):
    async def test_playlists_removed_in_yandex_are_deleted(self):
        kept = SimpleNamespace(kind="3", title="old")
        stale = SimpleNamespace(kind="9", title="gone")
        result = MagicMock()
        result.scalars.return_value.all.return_value = [kept, stale]
        session = SimpleNamespace(
            execute=AsyncMock(return_value=result), delete=AsyncMock(),
            add=MagicMock(), commit=AsyncMock(),
        )
        with patch.object(crud, "get_user", AsyncMock(return_value=SimpleNamespace(id=1))):
            await crud.sync_playlists(session, 1, [SimpleNamespace(kind=3, title="new")])
        session.delete.assert_awaited_once_with(stale)
        self.assertEqual(kept.title, "new")
        session.add.assert_not_called()


class PlaylistSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=1, user_id=1))
        self.callback = SimpleNamespace(
            from_user=SimpleNamespace(id=1),
            message=SimpleNamespace(edit_reply_markup=AsyncMock()),
            answer=AsyncMock(),
        )
        self.patches = [
            patch.object(playlist_handlers, "async_session", lambda: _Session()),
            patch.object(crud, "get_user_playlists", AsyncMock(return_value=[])),
        ]
        for p in self.patches:
            p.start()

    async def asyncTearDown(self):
        for p in self.patches:
            p.stop()

    async def select(self, selected):
        with patch.object(crud, "set_active_playlist", AsyncMock(return_value=selected)):
            await playlist_handlers.process_playlist_selection(
                self.callback, playlist_handlers.PlaylistCallback(id=5, action="select"), self.state,
            )

    async def test_switch_during_upload_mode_changes_target(self):
        await self.state.set_state(UserSteps.uploading)
        await self.state.update_data(token="t", playlist_kind="3")
        await self.select(SimpleNamespace(kind="7"))
        self.assertEqual((await self.state.get_data())["playlist_kind"], "7")

    async def test_missing_playlist_is_reported(self):
        await self.select(None)
        self.assertTrue(self.callback.answer.await_args.kwargs.get("show_alert"))
        self.callback.message.edit_reply_markup.assert_not_awaited()


class WaitForBotApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_until_local_api_is_up(self):
        bot = SimpleNamespace(delete_webhook=AsyncMock(side_effect=[
            TelegramNetworkError(method=MagicMock(), message="DNS"), True,
        ]))
        with patch.object(main, "API_WAIT_DELAY", 0):
            await main.wait_for_bot_api(bot, MagicMock())
        self.assertEqual(bot.delete_webhook.await_count, 2)

    async def test_gives_up_after_limit(self):
        bot = SimpleNamespace(delete_webhook=AsyncMock(
            side_effect=TelegramNetworkError(method=MagicMock(), message="DNS")))
        with patch.object(main, "API_WAIT_DELAY", 0), patch.object(main, "API_WAIT_ATTEMPTS", 3):
            with self.assertRaises(TelegramNetworkError):
                await main.wait_for_bot_api(bot, MagicMock())
        self.assertEqual(bot.delete_webhook.await_count, 3)


if __name__ == "__main__":
    unittest.main()
