"""Real loopback sockets, synthetic OAuth data; never provider traffic or user vault."""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp
import pytest

from openrouter_video import oauth
from openrouter_video.comfy.oauth_loopback import _STYLE, LoopbackReceiver


@pytest.mark.parametrize("browser_theme", ["light", "dark"])
def test_result_page_contrast_does_not_inherit_browser_theme(browser_theme: str) -> None:
    import re

    def luminance(hex_color: str) -> float:
        channels = [int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

    # Both opaque layers override either UA canvas palette; no theme-dependent branch.
    assert browser_theme in ("light", "dark")
    assert "@media" not in _STYLE
    for selector in ("html", "body"):
        rule = re.search(rf"{selector}\{{([^}}]+)\}}", _STYLE)
        assert rule is not None
        background = re.search(r"background:#([0-9a-f]{6})(?:;|$)", rule[1])
        foreground = re.search(r"(?:^|;)color:#([0-9a-f]{6})(?:;|$)", rule[1])
        assert background and foreground
        light, dark = sorted((luminance(background[1]), luminance(foreground[1])), reverse=True)
        assert (light + 0.05) / (dark + 0.05) >= 7  # WCAG AAA normal text.


def transaction(url: str) -> tuple[str, str]:
    query = parse_qs(urlparse(url).query)
    callback = query["callback_url"][0]
    state = parse_qs(urlparse(callback).query)["state"][0]
    assert query["code_challenge_method"] == ["S256"]
    return callback, state


@pytest.mark.parametrize("success", [True, False])
def test_raw_utf8_result_page_delivered_in_full_before_cleanup(success: bool) -> None:
    async def run() -> None:
        async def complete(state: str, code: str) -> bool:
            if not success:
                raise RuntimeError("TEST_ONLY_SECRET_DIAGNOSTIC")
            return True

        receiver = LoopbackReceiver(complete)
        callback, state = transaction(await receiver.start())
        parsed = urlparse(callback)
        reader, writer = await asyncio.open_connection("127.0.0.1", parsed.port)
        try:
            target = parsed.path + "?" + parsed.query + "&code=TEST_ONLY_CODE"
            writer.write(
                (
                    f"GET {target} HTTP/1.1\r\nHost: 127.0.0.1:{parsed.port}\r\n"
                    "Connection: close\r\nSec-Fetch-Site: cross-site\r\n\r\n"
                ).encode("ascii")
            )
            await writer.drain()
            raw = await asyncio.wait_for(reader.read(), 3)
            head, body = raw.split(b"\r\n\r\n", 1)
            lines = head.decode("ascii").split("\r\n")
            assert lines[0] == ("HTTP/1.1 200 OK" if success else "HTTP/1.1 400 Bad Request")
            headers = dict(line.split(": ", 1) for line in lines[1:])
            assert headers["Content-Type"] == "text/html; charset=utf-8"
            assert int(headers["Content-Length"]) == len(body) > 0
            html = body.decode("utf-8", errors="strict")
            assert len(body) > len(html)
            assert html.startswith('<!doctype html><html lang="ru"><head>')
            assert html.endswith("</main></body></html>")
            assert (
                "OpenRouter успешно подключён." if success else "Не удалось подключить OpenRouter."
            ) in html
            assert "Это окно можно закрыть и вернуться в ComfyUI." in html
            assert "background:#111827;color:#f9fafb" in html
            assert "style-src 'sha256-" in headers["Content-Security-Policy"]
            assert "default-src 'none'" in headers["Content-Security-Policy"]
            for forbidden in (state, "TEST_ONLY", "<script", "http://", "https://"):
                assert forbidden not in html
            await asyncio.wait_for(receiver.closed.wait(), 3)
            with pytest.raises(OSError):
                await asyncio.open_connection("127.0.0.1", parsed.port)
        finally:
            writer.close()
            await writer.wait_closed()
            await receiver.close()

    asyncio.run(run())


def test_real_loopback_success_ephemeral_cleanup_and_no_query_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def run() -> None:
        calls: list[tuple[str, str]] = []

        async def complete(state: str, code: str) -> bool:
            calls.append((state, code))
            return True

        receiver = LoopbackReceiver(complete)
        url = await receiver.start()
        callback, state = transaction(url)
        parsed = urlparse(callback)
        assert parsed.hostname == "127.0.0.1" and parsed.port and parsed.port != 8192
        assert parsed.path == "/callback"
        assert receiver._runner is not None
        assert receiver._runner.addresses == [("127.0.0.1", parsed.port)]
        async with aiohttp.ClientSession() as client:
            async with client.get(
                callback + "&code=TEST_ONLY_CODE", headers={"Sec-Fetch-Site": "cross-site"}
            ) as response:
                assert response.status == 200
                body = await response.text()
                assert "OpenRouter успешно подключён." in body
                assert response.headers["Cache-Control"] == "no-store"
                assert state not in body and "TEST_ONLY_CODE" not in body
                assert "<script" not in body and "https://" not in body
            await asyncio.wait_for(receiver.closed.wait(), 2)
            with pytest.raises(aiohttp.ClientConnectorError):
                await client.get(receiver.redirect_uri)
        assert calls == [(state, "TEST_ONLY_CODE")]
        assert state not in oauth._sessions

    asyncio.run(run())
    assert "TEST_ONLY_CODE" not in caplog.text
    assert "code_verifier" not in caplog.text


@pytest.mark.parametrize(
    "fault", ["wrong_state", "missing_state", "missing_code", "duplicate_state", "declined"]
)
def test_invalid_callback_is_rejected_and_cleaned(fault: str) -> None:
    async def run() -> None:
        calls: list[str] = []

        async def forbidden(state: str, code: str) -> bool:
            calls.append(code)
            return True

        receiver = LoopbackReceiver(forbidden)
        callback, state = transaction(await receiver.start())
        params: list[tuple[str, str]] = [("state", state), ("code", "TEST_ONLY_CODE")]
        if fault == "wrong_state":
            params[0] = ("state", "WRONG_STATE")
        if fault == "missing_state":
            params.pop(0)
        if fault == "missing_code":
            params.pop()
        if fault == "duplicate_state":
            params.append(("state", state))
        if fault == "declined":
            params.append(("error", "access_denied"))
        async with (
            aiohttp.ClientSession() as client,
            client.get(receiver.redirect_uri + "?" + urlencode(params)) as response,
        ):
            assert response.status == 400
            body = await response.text()
            assert "Не удалось подключить OpenRouter." in body
            assert state not in body and "TEST_ONLY_CODE" not in body
        await asyncio.wait_for(receiver.closed.wait(), 2)
        assert state not in oauth._sessions
        assert calls == []

    asyncio.run(run())


def test_duplicate_inflight_callback_does_not_exchange_twice() -> None:
    async def run() -> None:
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def complete(state: str, code: str) -> bool:
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()
            return True

        receiver = LoopbackReceiver(complete)
        callback, _ = transaction(await receiver.start())
        async with aiohttp.ClientSession() as client:

            async def first() -> int:
                async with client.get(callback + "&code=TEST_ONLY_CODE") as response:
                    await response.read()
                    return response.status

            task = asyncio.create_task(first())
            await entered.wait()
            async with client.get(callback + "&code=TEST_ONLY_DUPLICATE") as response:
                assert response.status == 410
            release.set()
            assert await task == 200
        await asyncio.wait_for(receiver.closed.wait(), 2)
        assert calls == 1

    asyncio.run(run())


def test_expired_listener_discards_verifier_and_closes_port() -> None:
    async def run() -> None:
        async def forbidden(state: str, code: str) -> bool:
            raise AssertionError("Expired transaction was accepted")

        receiver = LoopbackReceiver(forbidden, timeout=0.02)
        _, state = transaction(await receiver.start())
        await asyncio.wait_for(receiver.closed.wait(), 2)
        assert state not in oauth._sessions
        async with aiohttp.ClientSession() as client:
            with pytest.raises(aiohttp.ClientConnectorError):
                await client.get(receiver.redirect_uri)

    asyncio.run(run())


def test_failed_exchange_closes_listener_and_sanitizes_page() -> None:
    async def run() -> None:
        async def failure(state: str, code: str) -> bool:
            raise RuntimeError("TEST_ONLY_SECRET_ERROR")

        receiver = LoopbackReceiver(failure)
        callback, state = transaction(await receiver.start())
        async with (
            aiohttp.ClientSession() as client,
            client.get(callback + "&code=TEST_ONLY_CODE") as response,
        ):
            assert response.status == 400
            assert "TEST_ONLY" not in await response.text()
        await asyncio.wait_for(receiver.closed.wait(), 2)
        assert state not in oauth._sessions

    asyncio.run(run())


def test_start_route_owns_callback_and_replaces_previous_listener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from openrouter_video.comfy import compat, routes

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(routes, "_oauth_receiver", None)
    monkeypatch.setattr(routes, "_oauth_start_lock", None)
    monkeypatch.setattr(compat, "json_response", lambda payload, *, status: (payload, status))

    async def run() -> None:
        try:
            payload, status = await routes._auth_start_handler(None)
            assert status == 200
            _, old_state = transaction(payload["authorization_url"])
            old = routes._oauth_receiver
            payload, status = await routes._auth_start_handler(None)
            assert status == 200
            assert old is not None and old.closed.is_set()
            assert old_state not in oauth._sessions
            callback, _ = transaction(payload["authorization_url"])
            assert urlparse(callback).port != 8192
        finally:
            if routes._oauth_receiver is not None:
                await routes._oauth_receiver.close()

    asyncio.run(run())


def test_timeout_cancels_inflight_completion() -> None:
    async def run() -> None:
        entered, cancelled = asyncio.Event(), asyncio.Event()

        async def complete(state: str, code: str) -> bool:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
            return True

        receiver = LoopbackReceiver(complete, timeout=0.05)
        callback, state = transaction(await receiver.start())
        async with aiohttp.ClientSession() as client:
            try:
                async with client.get(callback + "&code=TEST_ONLY_CODE") as response:
                    assert response.status == 400
            except aiohttp.ServerDisconnectedError:
                pass
        assert entered.is_set()
        await asyncio.wait_for(receiver.closed.wait(), 2)
        assert cancelled.is_set()
        assert state not in oauth._sessions

    asyncio.run(run())
