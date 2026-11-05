import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web

from src.utils import oauth
from src.utils.yandex_proxy import YandexRequest


class OAuthGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_errors_switch_to_direct_and_close_response(self):
        for status in (502, 503, 504):
            with self.subTest(status=status), patch.object(oauth, "PROXY_URL", "configured"):
                response = MagicMock(status=status)
                proxy = MagicMock(post=AsyncMock(return_value=response))
                direct = MagicMock(post=AsyncMock(return_value="success"))
                self.assertEqual(await oauth._post(proxy, direct, "url", {}), "success")
                response.close.assert_called_once()
                direct.post.assert_awaited_once()

    async def test_auth_errors_do_not_switch_routes(self):
        with patch.object(oauth, "PROXY_URL", "configured"):
            response = MagicMock(status=400)
            proxy = MagicMock(post=AsyncMock(return_value=response))
            direct = MagicMock(post=AsyncMock())
            self.assertIs(await oauth._post(proxy, direct, "url", {}), response)
            direct.post.assert_not_awaited()


class APIGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.gateway_status = 504
        self.direct_calls = 0
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", self.handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.base = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
        self.request = YandexRequest(proxy_url=self.base)

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def handle(self, request):
        if request.raw_path.startswith("http://"):
            return web.Response(status=self.gateway_status, text="upstream request timeout")
        self.direct_calls += 1
        return web.Response(body=b'{"result":"ok"}')

    async def call(self, method):
        return await self.request._request_wrapper(
            method, self.base + "/data", proxy=self.base, timeout=2)

    async def test_504_read_succeeds_via_direct_connection(self):
        self.assertEqual(await self.call("GET"), b'{"result":"ok"}')
        self.assertEqual(self.direct_calls, 1)

    async def test_504_write_is_not_replayed(self):
        from yandex_music.exceptions import NetworkError
        with self.assertRaises(NetworkError):
            await self.call("POST")
        self.assertEqual(self.direct_calls, 0)

    async def test_unauthorized_read_is_not_replayed(self):
        from yandex_music.exceptions import UnauthorizedError
        self.gateway_status = 401
        with self.assertRaises(UnauthorizedError):
            await self.call("GET")
        self.assertEqual(self.direct_calls, 0)

    async def test_socks_connection_failure_falls_back_for_reads(self):
        # The HTTP server cannot complete a SOCKS handshake.
        self.request = YandexRequest(proxy_url=self.base.replace("http://", "socks5://"))
        self.assertEqual(await self.call("GET"), b'{"result":"ok"}')
        self.assertEqual(self.direct_calls, 1)
