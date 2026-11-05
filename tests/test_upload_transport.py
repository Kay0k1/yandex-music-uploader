import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiohttp
from aiohttp import web

from src.utils import async_uploader as uploader


class UploadTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.proxy_patch = patch.object(uploader, "HTTP_PROXY_URL", None)
        self.proxy_patch.start()
        self.status = 201
        self.body = '{"result": "CREATED"}'
        self.received = b""
        self.upload_calls = 0
        self.target_calls = 0
        self.fail_first_upload = False
        self.fail_first_target = False
        self.target_status = 200
        self.redirect_requests = 0
        app = web.Application()
        app.router.add_post("/target", self.target)
        app.router.add_post("/upload", self.upload)
        app.router.add_get("/redirect", self.redirect)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.base = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "track.mp3"
        self.path.write_bytes(b"audio-data" * 1000)
        self.session = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()
        self.directory.cleanup()
        self.proxy_patch.stop()

    async def target(self, request):
        self.target_calls += 1
        if self.fail_first_target and self.target_calls == 1:
            return web.Response(status=504, text="upstream request timeout")
        if self.target_status != 200:
            return web.Response(status=self.target_status, text="denied")
        return web.json_response({"post-target": self.base + "/upload",
                                  "ugc-track-id": "track-id"})

    async def upload(self, request):
        self.upload_calls += 1
        multipart = await request.multipart()
        field = await multipart.next()
        self.received = bytes(await field.read())
        if self.fail_first_upload and self.upload_calls == 1:
            return web.Response(status=502)
        headers = {"Location": self.base + "/redirect"} if self.status == 302 else {}
        return web.Response(status=self.status, text=self.body, headers=headers)

    async def redirect(self, request):
        self.redirect_requests += 1
        return web.Response(text="OK")

    async def acquire(self):
        return await uploader._acquire_target_and_upload(
            self.session, self.base + "/target?playlist-id=42:10", {},
            str(self.path), "track.mp3", 1,
        )

    async def test_created_response_uploads_entire_file(self):
        self.assertEqual(await self.acquire(), "track-id")
        self.assertEqual(self.received, self.path.read_bytes())

    async def test_gateway_timeout_on_target_uses_direct_fallback(self):
        self.fail_first_target = True
        with patch.object(uploader, "PROXY_URL", "socks5://example:1080"):
            self.assertEqual(await self.acquire(), "track-id")
        self.assertEqual(self.target_calls, 2)
        self.assertEqual(self.upload_calls, 1)
        self.assertEqual(self.received, self.path.read_bytes())

    async def test_empty_response_requires_playlist_confirmation(self):
        self.status, self.body = 200, ""
        with patch.object(uploader, "_confirm_uploaded_track", AsyncMock(return_value=True)) as verify:
            self.assertEqual(await self.acquire(), "track-id")
            verify.assert_awaited_once()

    async def test_empty_response_without_track_remains_failure(self):
        self.status, self.body = 200, ""
        with patch.object(uploader, "_confirm_uploaded_track", AsyncMock(return_value=False)):
            with self.assertRaises(uploader._RetryableUploadError):
                await self.acquire()

    async def test_redirect_cannot_be_mistaken_for_success(self):
        self.status, self.body = 302, ""
        with self.assertRaises(uploader._RetryableUploadError):
            await self.acquire()
        self.assertEqual(self.redirect_requests, 0)

    async def test_failed_server_response_is_retryable(self):
        self.status, self.body = 502, "Bad Gateway"
        with patch.object(uploader, "_confirm_uploaded_track", AsyncMock()) as verify:
            with self.assertRaises(uploader._RetryableUploadError):
                await self.acquire()
            verify.assert_not_awaited()

    async def test_lost_response_is_checked_in_playlist_before_retry(self):
        with patch.object(uploader, "_post_upload", AsyncMock(side_effect=asyncio.TimeoutError())), \
                patch.object(uploader, "_confirm_uploaded_track", AsyncMock(return_value=True)) as verify:
            self.assertEqual(await self.acquire(), "track-id")
            verify.assert_awaited_once()
        self.assertEqual(self.target_calls, 1)

    async def test_lost_response_without_track_in_playlist_is_retryable(self):
        with patch.object(uploader, "_post_upload", AsyncMock(side_effect=asyncio.TimeoutError())), \
                patch.object(uploader, "_confirm_uploaded_track", AsyncMock(return_value=False)):
            with self.assertRaises(uploader._RetryableUploadError):
                await self.acquire()

    async def test_unsent_file_skips_playlist_check(self):
        refused = uploader.PROXY_ERRORS[0](111, "connection refused")
        with patch.object(uploader, "_post_upload", AsyncMock(side_effect=refused)), \
                patch.object(uploader, "_confirm_uploaded_track", AsyncMock()) as verify:
            with self.assertRaises(uploader._RetryableUploadError):
                await self.acquire()
            verify.assert_not_awaited()

    async def test_rejected_token_is_not_retried(self):
        self.target_status = 401
        with self.assertRaises(uploader.UploadAuthError):
            await self.acquire()
        self.assertEqual(self.target_calls, 1)

    async def test_backup_route_reuses_target_and_resends_full_file(self):
        self.fail_first_upload = True
        with patch.object(uploader, "PROXY_URL", "socks5://example:1080"):
            self.assertEqual(await self.acquire(), "track-id")
        self.assertEqual(self.target_calls, 1)
        self.assertEqual(self.upload_calls, 2)
        self.assertEqual(self.received, self.path.read_bytes())

    async def test_successful_direct_upload_does_not_use_backup(self):
        with patch.object(uploader, "PROXY_URL", "socks5://example:1080"):
            self.assertEqual(await self.acquire(), "track-id")
        self.assertEqual(self.upload_calls, 1)

    async def test_error_containing_ok_is_not_success(self):
        self.body = '{"result": "NOT OK"}'
        with patch.object(uploader, "_confirm_uploaded_track", AsyncMock(return_value=False)):
            with self.assertRaises(uploader._RetryableUploadError):
                await self.acquire()


if __name__ == "__main__":
    unittest.main()
