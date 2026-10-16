"""OpenRouter's documented PKCE flow with process-local state and no key exposure."""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

import httpx

from openrouter_video.errors import RequestPolicyError

_AUTH_URL = "https://openrouter.ai/auth"
_EXCHANGE_URL = "https://openrouter.ai/api/v1/auth/keys"
_CALLBACK_PATH = "/openrouter-video/v1/auth/callback"
_SESSION_TTL_SECONDS = 600


@dataclass(frozen=True, slots=True)
class PkceSession:
    verifier: str
    callback_url: str
    created_at: float


_sessions: dict[str, PkceSession] = {}
_lock = threading.RLock()


def _valid_callback_url(value: object) -> str:
    if not isinstance(value, str):
        raise RequestPolicyError("OpenRouter connection callback is invalid")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise RequestPolicyError("OpenRouter connection is available only from this local ComfyUI")
    if parsed.path != _CALLBACK_PATH or parsed.query or parsed.fragment:
        raise RequestPolicyError("OpenRouter connection callback is invalid")
    return value


def begin(callback_url: str, *, now: float | None = None) -> tuple[str, str]:
    """Create one short-lived PKCE session and return ``(state, authorization_url)``."""

    import time

    callback = _valid_callback_url(callback_url)
    timestamp = time.time() if now is None else now
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state = secrets.token_urlsafe(32)
    with _lock:
        _prune(timestamp)
        _sessions[state] = PkceSession(verifier, callback, timestamp)
    query = urlencode(
        {
            "callback_url": callback,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    return state, f"{_AUTH_URL}?{query}"


def _prune(now: float) -> None:
    expired = [
        key for key, session in _sessions.items() if now - session.created_at > _SESSION_TTL_SECONDS
    ]
    for key in expired:
        _sessions.pop(key, None)


async def exchange(state: str, code: str) -> str:
    """Exchange one callback code for an OpenRouter user-controlled API key."""

    import time

    if not isinstance(state, str) or not state or not isinstance(code, str) or not code:
        raise RequestPolicyError("OpenRouter authorization response is incomplete")
    with _lock:
        _prune(time.time())
        session = _sessions.pop(state, None)
    if session is None:
        raise RequestPolicyError("OpenRouter authorization expired; start again")
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(20.0, connect=10.0),
        ) as client:
            response = await client.post(
                _EXCHANGE_URL,
                json={
                    "code": code,
                    "code_verifier": session.verifier,
                    "code_challenge_method": "S256",
                },
            )
    except httpx.HTTPError:
        raise RequestPolicyError("OpenRouter authorization could not reach OpenRouter") from None
    if response.status_code != 200:
        raise RequestPolicyError("OpenRouter authorization was declined or expired")
    try:
        payload = response.json()
        key = payload["key"]
    except (ValueError, KeyError, TypeError):
        raise RequestPolicyError("OpenRouter authorization response is invalid") from None
    if not isinstance(key, str) or not key.strip():
        raise RequestPolicyError("OpenRouter authorization response is invalid")
    return key.strip()


__all__ = ("_CALLBACK_PATH", "begin", "exchange")
