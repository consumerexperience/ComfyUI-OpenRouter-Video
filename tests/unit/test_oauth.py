"""PKCE shape and callback validation without contacting OpenRouter."""

import asyncio
import json
from typing import cast
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from openrouter_video import oauth
from openrouter_video.errors import RequestPolicyError


def test_begin_builds_localhost_s256_authorization_url() -> None:
    state, url = oauth.begin("http://127.0.0.1:49152/callback", now=1000.0)
    assert state
    query = parse_qs(urlparse(url).query)
    redirect = urlparse(query["callback_url"][0])
    assert redirect.hostname == "127.0.0.1" and redirect.port == 49152
    assert redirect.path == "/callback"
    assert parse_qs(redirect.query)["state"] == [state]
    assert query["code_challenge_method"] == ["S256"]
    assert "TEST_ONLY" not in json.dumps([state, url])


@pytest.mark.parametrize(
    "callback", ["https://evil.example/callback", "http://127.0.0.1:8189/other"]
)
def test_begin_rejects_non_local_callback(callback: str) -> None:
    with pytest.raises(RequestPolicyError):
        oauth.begin(callback)


def test_exchange_uses_verifier_once_without_logging_key(monkeypatch: pytest.MonkeyPatch) -> None:
    state, _ = oauth.begin("http://127.0.0.1:49152/callback")
    captured: dict[str, object] = {}

    class Response:
        status_code = 200

        def json(self) -> object:
            return {"key": "TEST_ONLY_OAUTH_KEY"}

    class Client:
        async def __aenter__(self) -> "Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> Response:
            captured.update(kwargs)
            assert url == "https://openrouter.ai/api/v1/auth/keys"
            return Response()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: Client())
    key = asyncio.run(oauth.exchange(state, "TEST_ONLY_CODE"))
    assert key == "TEST_ONLY_OAUTH_KEY"
    body = cast(dict[str, object], captured["json"])
    assert body["code_challenge_method"] == "S256"
    assert body["code_verifier"]
    with pytest.raises(RequestPolicyError):
        asyncio.run(oauth.exchange(state, "TEST_ONLY_CODE"))
