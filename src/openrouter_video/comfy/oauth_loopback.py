"""One short-lived, loopback-only OAuth callback receiver outside ComfyUI."""

from __future__ import annotations

import asyncio
import secrets
import socket
from collections.abc import Awaitable, Callable

from aiohttp import web

from openrouter_video.oauth import begin, cancel

_SUCCESS = "OpenRouter connected successfully."
_FAILURE = "OpenRouter connection could not be completed."
Complete = Callable[[str, str], Awaitable[bool]]


def _page(success: bool, status: int = 200) -> web.Response:
    message = _SUCCESS if success else _FAILURE
    return web.Response(
        text=(
            "<!doctype html><html lang=en><meta charset=utf-8>"
            "<title>OpenRouter connection</title><h1>" + message + "</h1>"
            "<p>You can close this tab and return to ComfyUI.</p></html>"
        ),
        content_type="text/html",
        status=status,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            "X-Content-Type-Options": "nosniff",
        },
    )


class LoopbackReceiver:
    """Own one transaction; no request/query/access logging, no durable temporary state."""

    def __init__(self, complete: Complete, timeout: float = 600.0) -> None:
        self._complete = complete
        self._timeout = timeout
        self._runner: web.AppRunner | None = None
        self._timer: asyncio.Task[None] | None = None
        self._state = ""
        self._consumed = False
        self._closing = False
        self._deadline = 0.0
        self.closed = asyncio.Event()
        self.redirect_uri = ""

    async def start(self) -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", 0))
            sock.setblocking(False)
            self.redirect_uri = f"http://127.0.0.1:{sock.getsockname()[1]}/callback"
            app = web.Application(client_max_size=4096)
            app.router.add_get("/callback", self._callback, allow_head=False)
            self._runner = web.AppRunner(app, access_log=None, shutdown_timeout=1.0)
            await self._runner.setup()
            await web.SockSite(self._runner, sock).start()
            self._state, url = begin(self.redirect_uri)
            self._deadline = asyncio.get_running_loop().time() + self._timeout
            self._timer = asyncio.create_task(self._expire())
            return url
        except BaseException:
            sock.close()
            await self.close()
            raise

    async def _expire(self) -> None:
        await asyncio.sleep(self._timeout)
        await self.close()

    async def _callback(self, request: web.Request) -> web.Response:
        if self._consumed or self._closing:
            return _page(False, 410)
        self._consumed = True
        try:
            remaining = self._deadline - asyncio.get_running_loop().time()
            states = request.query.getall("state", [])
            codes = request.query.getall("code", [])
            if (
                remaining <= 0
                or request.query.get("error")
                or len(states) != 1
                or len(codes) != 1
                or not codes[0]
                or len(codes[0]) > 4096
                or not secrets.compare_digest(states[0], self._state)
            ):
                return _page(False, 400)
            success = await asyncio.wait_for(self._complete(states[0], codes[0]), remaining)
            return _page(success, 200 if success else 400)
        except Exception:
            return _page(False, 400)
        finally:
            # Cleanup must run after the response handler returns, not await itself.
            asyncio.create_task(self.close())

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        cancel(self._state)
        self._state = ""
        if self._timer is not None and self._timer is not asyncio.current_task():
            self._timer.cancel()
        try:
            if self._runner is not None:
                await self._runner.cleanup()
        finally:
            self.closed.set()
