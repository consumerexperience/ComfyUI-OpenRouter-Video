"""One short-lived, loopback-only OAuth callback receiver outside ComfyUI."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import socket
from collections.abc import Awaitable, Callable

from aiohttp import web

from openrouter_video.oauth import begin, cancel

from .oauth_diagnostics import Outcome, callback_outcomes

_SUCCESS = "OpenRouter успешно подключён."
_FAILURE = "Не удалось подключить OpenRouter."
_RETURN = "Это окно можно закрыть и вернуться в ComfyUI."
_STYLE = (
    "html{color-scheme:light dark;background:#111827;color:#f9fafb}"
    "body{margin:0;min-height:100vh;box-sizing:border-box;display:grid;"
    "place-items:center;padding:24px;background:#111827;color:#f9fafb;"
    "font:16px/1.6 system-ui,sans-serif}"
    "main{width:100%;max-width:32rem;text-align:center;overflow-wrap:anywhere}"
    "h1{font-size:1.5rem;line-height:1.3;margin:0 0 16px}p{margin:0}"
)
_STYLE_HASH = base64.b64encode(hashlib.sha256(_STYLE.encode("utf-8")).digest()).decode("ascii")
Complete = Callable[[str, str], Awaitable[bool]]
_RESULT_TTL_SECONDS = 5.0


def _page(success: bool, status: int = 200) -> web.Response:
    message = _SUCCESS if success else _FAILURE
    return web.Response(
        body=(
            '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>Подключение OpenRouter</title><style>" + _STYLE + "</style></head>"
            "<body><main><h1>" + message + "</h1><p>" + _RETURN + "</p></main></body></html>"
        ).encode("utf-8"),
        content_type="text/html",
        charset="utf-8",
        status=status,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'none'; frame-ancestors 'none'; style-src 'sha256-" + _STYLE_HASH + "'"
            ),
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
        self._request_digest: bytes | None = None
        self._terminal_success = False
        self._result_deadline = 0.0
        self._finished = asyncio.Event()
        self._cleanup: asyncio.Task[None] | None = None
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
        callback_outcomes.record(Outcome.DEADLINE)
        await self.close()

    async def _callback(self, request: web.Request) -> web.Response:
        if self._consumed or self._closing:
            callback_outcomes.record(
                Outcome.DUPLICATE if self._consumed else Outcome.RECEIVER_CLOSING
            )
            if self._consumed:
                return await self._repeat(request)
            return _page(False, 410)
        self._consumed = True
        try:
            remaining = self._deadline - asyncio.get_running_loop().time()
            states = request.query.getall("state", [])
            codes = request.query.getall("code", [])
            rejection = None
            if remaining <= 0:
                rejection = Outcome.DEADLINE
            elif request.query.get("error"):
                rejection = Outcome.PROVIDER_ERROR
            elif len(states) != 1 or len(codes) != 1 or not codes[0] or len(codes[0]) > 4096:
                rejection = Outcome.INVALID_CALLBACK_SHAPE
            elif not secrets.compare_digest(states[0], self._state):
                rejection = Outcome.STATE_MISMATCH
            if rejection is not None:
                callback_outcomes.record(rejection)
                return _page(False, 400)
            self._request_digest = self._digest(states[0], codes[0])
            success = await asyncio.wait_for(self._complete(states[0], codes[0]), remaining)
            self._terminal_success = success
            if success:
                self._result_deadline = min(
                    self._deadline, asyncio.get_running_loop().time() + _RESULT_TTL_SECONDS
                )
            callback_outcomes.record(Outcome.SUCCESS if success else Outcome.COMPLETION_FAILED)
            return _page(success, 200 if success else 400)
        except asyncio.TimeoutError:
            callback_outcomes.record(Outcome.DEADLINE)
            return _page(False, 400)
        except Exception:
            callback_outcomes.record(Outcome.UNEXPECTED_FAILURE)
            return _page(False, 400)
        finally:
            # The verifier/raw state are not retained for result replay.
            cancel(self._state)
            self._state = ""
            self._finished.set()
            # Cleanup must run after the response handler returns, not await itself.
            self._cleanup = asyncio.create_task(self._close_after_result())

    @staticmethod
    def _digest(state: str, code: str) -> bytes:
        return hashlib.sha256(state.encode("utf-8") + b"\0" + code.encode("utf-8")).digest()

    async def _repeat(self, request: web.Request) -> web.Response:
        """Return this transaction's result only; never repeat completion work."""
        if self._closing:
            return _page(False, 410)
        remaining = self._deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            callback_outcomes.record(Outcome.DEADLINE)
            return _page(False, 410)
        states = request.query.getall("state", [])
        codes = request.query.getall("code", [])
        if (
            request.query.get("error")
            or len(states) != 1
            or len(codes) != 1
            or not states[0]
            or not codes[0]
            or len(states[0]) > 128
            or len(codes[0]) > 4096
            or self._request_digest is None
            or not secrets.compare_digest(self._digest(states[0], codes[0]), self._request_digest)
        ):
            return _page(False, 410)
        try:
            await asyncio.wait_for(self._finished.wait(), remaining)
        except asyncio.TimeoutError:
            callback_outcomes.record(Outcome.DEADLINE)
            return _page(False, 410)
        if (
            self._terminal_success
            and not self._closing
            and asyncio.get_running_loop().time() < self._result_deadline
        ):
            callback_outcomes.record(Outcome.RESULT_REPLAYED)
            return _page(True)
        return _page(False, 410)

    async def _close_after_result(self) -> None:
        if self._terminal_success:
            await asyncio.sleep(max(0, self._result_deadline - asyncio.get_running_loop().time()))
        await self.close()

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._finished.set()
        self._request_digest = None
        self._terminal_success = False
        self._result_deadline = 0.0
        if self._cleanup is not None and self._cleanup is not asyncio.current_task():
            self._cleanup.cancel()
        cancel(self._state)
        self._state = ""
        if self._timer is not None and self._timer is not asyncio.current_task():
            self._timer.cancel()
        try:
            if self._runner is not None:
                await self._runner.cleanup()
        finally:
            self._request_digest = None
            self._terminal_success = False
            self._result_deadline = 0.0
            if self._cleanup is not None and self._cleanup is not asyncio.current_task():
                self._cleanup.cancel()
            self.closed.set()
