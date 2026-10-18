"""A result belongs only to its original callback; no repeated completion work."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from urllib.parse import parse_qs, urlparse

import aiohttp
import pytest
from aiohttp import web

from openrouter_video import oauth
from openrouter_video.comfy import oauth_loopback


def callback_from(auth: str) -> str:
    return parse_qs(urlparse(auth).query)["callback_url"][0]


def request_for(callback: str, code: str = "TEST_ONLY_CODE") -> web.Request:
    values = parse_qs(urlparse(callback).query)
    values["code"] = [code]
    query = SimpleNamespace(
        getall=lambda name, default: values.get(name, default),
        get=lambda name: values[name][0] if name in values else None,
    )
    return cast(web.Request, SimpleNamespace(query=query))


def test_terminal_replay_is_exact_and_does_not_accept_other_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oauth_loopback, "_RESULT_TTL_SECONDS", 2.0)

    async def run() -> None:
        calls = 0

        async def complete(state: str, code: str) -> bool:
            nonlocal calls
            calls += 1
            return True

        receiver = oauth_loopback.LoopbackReceiver(complete)
        callback = callback_from(await receiver.start())
        state = parse_qs(urlparse(callback).query)["state"][0]
        other = oauth_loopback.LoopbackReceiver(complete)
        other_callback = callback_from(await other.start())
        try:
            async with aiohttp.ClientSession() as client:
                async with client.get(callback + "&code=TEST_ONLY_CODE") as response:
                    assert response.status == 200
                    expected = await response.read()
                assert state not in oauth._sessions
                assert receiver._state == ""
                for _ in range(2):
                    async with client.get(callback + "&code=TEST_ONLY_CODE") as response:
                        assert response.status == 200
                        assert await response.read() == expected
                invalid_queries = [
                    "",
                    "?state=WRONG&code=TEST_ONLY_CODE",
                    "?code=TEST_ONLY_CODE",
                    urlparse(callback).query.join(["?", "&code=WRONG"]),
                    "?" + urlparse(other_callback).query + "&code=TEST_ONLY_CODE",
                    "?" + urlparse(callback).query + "&code=TEST_ONLY_CODE&state=WRONG",
                    "?" + urlparse(callback).query + "&code=TEST_ONLY_CODE&error=denied",
                ]
                for query in invalid_queries:
                    async with client.get(receiver.redirect_uri + query) as response:
                        assert response.status == 410
                        body = await response.text()
                        assert "Не удалось подключить OpenRouter." in body
                        assert "успешно подключён" not in body
                assert calls == 1
                # A successful *different* receiver cannot bless this failed transaction.
                async with client.get(other_callback + "&code=TEST_ONLY_CODE") as response:
                    assert response.status == 200
                assert calls == 2
        finally:
            await receiver.close()
            await other.close()
        assert receiver._request_digest is None
        assert receiver._terminal_success is False

    asyncio.run(run())


def test_failed_transaction_duplicate_never_becomes_success() -> None:
    async def run() -> None:
        calls = 0

        async def failed(state: str, code: str) -> bool:
            nonlocal calls
            calls += 1
            return False

        receiver = oauth_loopback.LoopbackReceiver(failed)
        callback = callback_from(await receiver.start())
        response = await receiver._callback(request_for(callback))
        assert response.status == 400
        duplicate = await receiver._callback(request_for(callback))
        assert duplicate.status == 410
        assert duplicate.text is not None
        assert "Не удалось подключить OpenRouter." in duplicate.text
        assert calls == 1
        await receiver.close()

    asyncio.run(run())


def test_original_deadline_overrides_success_cache_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oauth_loopback, "_RESULT_TTL_SECONDS", 30.0)

    async def run() -> None:
        async def complete(state: str, code: str) -> bool:
            return True

        receiver = oauth_loopback.LoopbackReceiver(complete, timeout=0.1)
        callback = callback_from(await receiver.start())
        assert (await receiver._callback(request_for(callback))).status == 200
        await asyncio.wait_for(receiver.closed.wait(), 2)
        assert receiver._request_digest is None
        assert not receiver._terminal_success
        assert (await receiver._callback(request_for(callback))).status == 410

    asyncio.run(run())


def test_expired_request_cannot_replay_success() -> None:
    async def run() -> None:
        async def complete(state: str, code: str) -> bool:
            return True

        receiver = oauth_loopback.LoopbackReceiver(complete)
        callback = callback_from(await receiver.start())
        assert (await receiver._callback(request_for(callback))).status == 200
        receiver._deadline = asyncio.get_running_loop().time() - 1
        assert (await receiver._callback(request_for(callback))).status == 410
        await receiver.close()

    asyncio.run(run())


def test_replay_grace_expires_and_clears_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oauth_loopback, "_RESULT_TTL_SECONDS", 0.02)

    async def run() -> None:
        async def complete(state: str, code: str) -> bool:
            return True

        receiver = oauth_loopback.LoopbackReceiver(complete)
        callback = callback_from(await receiver.start())
        assert (await receiver._callback(request_for(callback))).status == 200
        await asyncio.wait_for(receiver.closed.wait(), 2)
        assert receiver._request_digest is None
        assert not receiver._terminal_success
        async with aiohttp.ClientSession() as client:
            with pytest.raises(aiohttp.ClientConnectorError):
                await client.get(callback + "&code=TEST_ONLY_CODE")

    asyncio.run(run())
