"""Shared HTTP/SOCKS transport for Yandex API, OAuth and uploads."""
import os
import logging

import aiohttp
from aiohttp_socks import ProxyConnector, ProxyConnectionError, ProxyError, ProxyTimeoutError
from yandex_music.exceptions import NetworkError
from yandex_music.utils.request_async import Request


PROXY_URL = os.getenv("YANDEX_PROXY_URL") or None
PROXY_ERRORS = (ProxyConnectionError, ProxyError, ProxyTimeoutError)
logger = logging.getLogger(__name__)


def _is_socks(url):
    return bool(url and url.lower().startswith(("socks4://", "socks5://")))


HTTP_PROXY_URL = None if _is_socks(PROXY_URL) else PROXY_URL


def create_yandex_session():
    connector = ProxyConnector.from_url(PROXY_URL) if _is_socks(PROXY_URL) else None
    return aiohttp.ClientSession(connector=connector)


class YandexRequest(Request):
    """Preserve the library's parsing and errors while using a SOCKS connector."""

    def __init__(self, *args, proxy_url=None, **kwargs):
        self._configured_proxy = proxy_url
        self._socks_url = proxy_url if _is_socks(proxy_url) else None
        super().__init__(*args, proxy_url=None if self._socks_url else proxy_url, **kwargs)

    async def _request_wrapper(self, *args, **kwargs):
        try:
            return await self._request_via_proxy(*args, **kwargs)
        except NetworkError:
            method = kwargs.get("method", args[0] if args else "")
            if not self._configured_proxy or str(method).upper() != "GET":
                raise
            # Only replay reads: writes may have succeeded before a gateway timed out.
            logger.warning("Yandex API proxy request failed; retrying read directly")
            kwargs["proxy"] = None
            return await super()._request_wrapper(*args, **kwargs)

    async def _request_via_proxy(self, *args, **kwargs):
        if not self._socks_url:
            return await super()._request_wrapper(*args, **kwargs)
        # aiohttp.request does not own explicitly supplied connectors.
        async with ProxyConnector.from_url(self._socks_url) as connector:
            kwargs["connector"] = connector
            kwargs["proxy"] = None
            try:
                return await super()._request_wrapper(*args, **kwargs)
            except PROXY_ERRORS as exc:
                raise NetworkError("SOCKS proxy connection failed") from exc
