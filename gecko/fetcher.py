"""HTTP fetcher — stealthy requests with TLS fingerprint impersonation."""
from __future__ import annotations

import time
from typing import Any

import anyio
from curl_cffi import requests as curl_requests
from curl_cffi.requests import BrowserTypeLiteral

from gecko.parser import Page

# curl_cffi supported impersonation targets: chrome99-131, firefox110-124,
# safari15_3-17_0, edge99-101. See: github.com/lexiforest/curl_cffi

_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
}


def _headers(overrides: dict | None = None) -> dict:
    if not overrides:
        return dict(_HEADERS)
    return dict(_HEADERS, **overrides)


class Response:
    __slots__ = ("status", "url", "headers", "cookies", "page", "json")

    def __init__(self, resp: curl_requests.Response):
        self.status = resp.status_code
        self.url = resp.url
        self.headers = resp.headers
        self.cookies = dict(resp.cookies)
        encoding = resp.encoding or "utf-8"

        ct = resp.headers.get("content-type", "")
        if ct.startswith("application/json"):
            self.page = Page("<html></html>")
            self.json = resp.json()
        else:
            self.page = Page(resp.content, url=resp.url, encoding=encoding)
            self.json = None

    def __repr__(self) -> str:
        return f"Response({self.status} {self.url})"


class Session:
    def __init__(
        self,
        impersonate: BrowserTypeLiteral | str = "chrome131",
        timeout: float = 30,
        retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self._impersonate = impersonate
        self._timeout = timeout
        self._retries = retries
        self._retry_delay = retry_delay
        self._session: curl_requests.Session | None = None

    def open(self) -> Session:
        self._session = curl_requests.Session(impersonate=self._impersonate, timeout=self._timeout)
        return self

    def close(self) -> None:
        if self._session:
            self._session.close()
            self._session = None

    def __enter__(self) -> Session:
        return self.open()

    def __exit__(self, *_: Any) -> None:
        self.close()

    def get(self, url: str, *, headers: dict | None = None, **kwargs) -> Response:
        return self._request("GET", url, headers=headers, **kwargs)

    def post(self, url: str, *, data: dict | None = None, json: dict | None = None,
             headers: dict | None = None, **kwargs) -> Response:
        return self._request("POST", url, data=data, json=json, headers=headers, **kwargs)

    def _request(self, method: str, url: str, **kwargs) -> Response:
        s = self._session or curl_requests.Session(impersonate=self._impersonate, timeout=self._timeout)
        kwargs.setdefault("headers", _headers(kwargs.get("headers")))
        kwargs.setdefault("allow_redirects", True)

        last_err = None
        for attempt in range(self._retries + 1):
            try:
                resp = s.request(method, url, **kwargs)
                resp.raise_for_status()
                return Response(resp)
            except Exception as e:
                last_err = e
                if attempt < self._retries:
                    time.sleep(self._retry_delay * (2 ** attempt))

        raise last_err  # type: ignore[misc]


class AsyncSession(Session):
    def open(self) -> AsyncSession:
        from curl_cffi.requests import AsyncSession as CurlAsync
        self._session = CurlAsync(impersonate=self._impersonate, timeout=self._timeout)
        return self

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> AsyncSession:
        return self.open()

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def get(self, url: str, *, headers: dict | None = None, **kwargs) -> Response:
        return await self._request("GET", url, headers=headers, **kwargs)

    async def post(self, url: str, *, data: dict | None = None, json: dict | None = None,
                   headers: dict | None = None, **kwargs) -> Response:
        return await self._request("POST", url, data=data, json=json, headers=headers, **kwargs)

    async def _request(self, method: str, url: str, **kwargs) -> Response:
        s = self._session
        if s is None:
            from curl_cffi.requests import AsyncSession as CurlAsync
            s = CurlAsync(impersonate=self._impersonate, timeout=self._timeout)
        kwargs.setdefault("headers", _headers(kwargs.get("headers")))
        kwargs.setdefault("allow_redirects", True)

        last_err = None
        for attempt in range(self._retries + 1):
            try:
                resp = await s.request(method, url, **kwargs)
                resp.raise_for_status()
                return Response(resp)
            except Exception as e:
                last_err = e
                if attempt < self._retries:
                    await anyio.sleep(self._retry_delay * (2 ** attempt))

        raise last_err  # type: ignore[misc]


def fetch(url: str, *, impersonate: BrowserTypeLiteral | str = "chrome131",
          timeout: float = 30, headers: dict | None = None, **kwargs) -> Response:
    s = curl_requests.Session(impersonate=impersonate, timeout=timeout)
    try:
        resp = s.get(url, headers=_headers(headers), allow_redirects=True, **kwargs)
        return Response(resp)
    finally:
        s.close()
