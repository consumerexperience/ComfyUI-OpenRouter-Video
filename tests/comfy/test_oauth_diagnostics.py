"""Sanitized process-memory diagnostics, synthetic completion and loopback only."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import aiohttp
import pytest

from openrouter_video.comfy import oauth_loopback, routes
from openrouter_video.comfy.oauth_diagnostics import CallbackOutcomes, Outcome


@pytest.fixture
def outcomes(monkeypatch: pytest.MonkeyPatch) -> CallbackOutcomes:
    memory = CallbackOutcomes()
    monkeypatch.setattr(oauth_loopback, "callback_outcomes", memory)
    monkeypatch.setattr(routes, "callback_outcomes", memory)
    return memory


def test_memory_is_bounded_strict_and_does_not_survive_new_instance() -> None:
    memory = CallbackOutcomes()
    with pytest.raises(TypeError):
        memory.record("TEST_ONLY_SECRET")  # type: ignore[arg-type]
    assert memory.snapshot() == []
    for _ in range(40):
        memory.record(Outcome.SUCCESS)
    assert memory.snapshot() == ["SUCCESS"] * 32
    copied = memory.snapshot()
    copied.clear()
    assert len(memory.snapshot()) == 32
    assert CallbackOutcomes().snapshot() == []


@pytest.mark.parametrize("phase", ["EXCHANGE_FAILED", "VALIDATION_FAILED", "STORE_FAILED"])
def test_completion_records_only_failed_stage(
    monkeypatch: pytest.MonkeyPatch, outcomes: CallbackOutcomes, phase: str
) -> None:
    canary = "TEST_ONLY_SECRET_STATE_CODE_VERIFIER_HTTPS_QUERY"

    async def exchange(state: str, code: str) -> str:
        if phase == "EXCHANGE_FAILED":
            raise RuntimeError(canary)
        return "TEST_ONLY_CREDENTIAL"

    async def validate() -> None:
        if phase == "VALIDATION_FAILED":
            raise RuntimeError(canary)

    def store(key: str) -> None:
        if phase == "STORE_FAILED":
            raise RuntimeError(canary)

    monkeypatch.setattr(routes, "openrouter_credential_source", lambda: "NONE")
    monkeypatch.setattr(routes, "exchange_pkce", exchange)
    monkeypatch.setattr(
        routes, "get_runtime", lambda: SimpleNamespace(validate_connection=validate)
    )
    monkeypatch.setattr(routes, "set_interactive_openrouter_api_key", store)
    assert not asyncio.run(routes._complete_oauth(canary, canary))
    assert outcomes.snapshot() == [phase]
    assert canary not in json.dumps(outcomes.snapshot())


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", "INVALID_CALLBACK_SHAPE"),
        ("?state=WRONG&code=TEST_ONLY", "STATE_MISMATCH"),
        ("?error=TEST_ONLY_SECRET", "PROVIDER_ERROR"),
    ],
)
def test_rejection_categories_contain_no_query_data(
    outcomes: CallbackOutcomes, query: str, expected: str
) -> None:
    async def run() -> None:
        async def forbidden(state: str, code: str) -> bool:
            raise AssertionError("Completion must not run")

        receiver = oauth_loopback.LoopbackReceiver(forbidden)
        await receiver.start()
        async with (
            aiohttp.ClientSession() as client,
            client.get(receiver.redirect_uri + query) as response,
        ):
            assert response.status == 400
            await response.read()
        await asyncio.wait_for(receiver.closed.wait(), 2)
        assert outcomes.snapshot() == [expected]

    asyncio.run(run())


def test_duplicate_and_success_both_retained(outcomes: CallbackOutcomes) -> None:
    async def run() -> None:
        entered, release = asyncio.Event(), asyncio.Event()

        async def complete(state: str, code: str) -> bool:
            entered.set()
            await release.wait()
            return True

        receiver = oauth_loopback.LoopbackReceiver(complete)
        callback = parse_qs(urlparse(await receiver.start()).query)["callback_url"][0]
        async with aiohttp.ClientSession() as client:

            async def first() -> int:
                async with client.get(callback + "&code=TEST_ONLY") as response:
                    await response.read()
                    return response.status

            task = asyncio.create_task(first())
            await entered.wait()
            async with client.get(callback + "&code=TEST_ONLY") as response:
                assert response.status == 410
            release.set()
            assert await task == 200
        await asyncio.wait_for(receiver.closed.wait(), 2)
        assert outcomes.snapshot() == ["DUPLICATE", "SUCCESS"]

    asyncio.run(run())


def test_timeout_category(outcomes: CallbackOutcomes) -> None:
    async def run() -> None:
        async def complete(state: str, code: str) -> bool:
            return True

        receiver = oauth_loopback.LoopbackReceiver(complete, timeout=0.01)
        await receiver.start()
        await asyncio.wait_for(receiver.closed.wait(), 2)
        assert outcomes.snapshot() == ["DEADLINE"]

    asyncio.run(run())


def test_read_only_route_returns_categories_with_no_store(
    monkeypatch: pytest.MonkeyPatch, outcomes: CallbackOutcomes
) -> None:
    outcomes.record(Outcome.SUCCESS)
    monkeypatch.setattr(
        routes.compat,
        "json_response",
        lambda payload, **kw: SimpleNamespace(payload=payload, status=kw["status"], headers={}),
    )
    response = asyncio.run(routes._oauth_diagnostics_handler(None))
    assert response.payload == {"outcomes": ["SUCCESS"]}
    assert response.status == 200
    assert response.headers == {"Cache-Control": "no-store"}
    assert outcomes.snapshot() == ["SUCCESS"]
