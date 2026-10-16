"""Real loopback sockets, synthetic OAuth data; never provider traffic or user vault."""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp
import pytest

from openrouter_video import oauth
from openrouter_video.comfy.oauth_loopback import LoopbackReceiver


def transaction(url: str) -> tuple[str, str]:
    query = parse_qs(urlparse(url).query)
    callback = query["callback_url"][0]
    state = parse_qs(urlparse(callback).query)["state"][0]
    assert query["code_challenge_method"] == ["S256"]
    return callback, state


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
                assert "OpenRouter connected successfully." in body
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
            assert "could not be completed" in body
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
