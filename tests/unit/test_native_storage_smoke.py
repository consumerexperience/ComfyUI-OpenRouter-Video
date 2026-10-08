"""Prepared smoke contract only: synthetic storage/client, no cloud calls."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from openrouter_video.s3_upload import StorageError
from tests.manual import native_media_storage_smoke as smoke


@pytest.mark.parametrize("deleted_status", [404, 200, 403])
def test_prepared_storage_smoke_verifies_exact_delete_absence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], deleted_status: int
) -> None:
    events: list[str] = []
    content = b""
    url = "https://offline.example.test/synthetic?signature=private-canary"

    class Uploader:
        def configuration_fingerprint(self) -> str:
            return "offline-owned-bucket"

        async def upload(self, key: str, path: Path, content_type: str) -> None:
            nonlocal content
            assert key.startswith("openrouter-video/staging/") and key.endswith(".wav")
            assert content_type == "audio/wav"
            content = path.read_bytes()
            events.append("PUT")

        async def presign_get(self, key: str) -> str:
            return url

        async def delete(self, key: str) -> None:
            events.append("DELETE")

    class Client:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs == {"follow_redirects": False, "trust_env": False, "timeout": 30}

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, supplied: str) -> httpx.Response:
            assert supplied == url
            events.append("GET")
            return httpx.Response(deleted_status if "DELETE" in events else 200, content=content)

    monkeypatch.setattr(smoke, "S3MediaUploader", Uploader)
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    if deleted_status == 404:
        asyncio.run(smoke.smoke())
        assert "exact DELETE and absence" in capsys.readouterr().out
    else:
        with pytest.raises(StorageError, match="cleanup is unverified"):
            asyncio.run(smoke.smoke())
    assert events == ["PUT", "GET", "DELETE", "GET"]
    assert "private-canary" not in capsys.readouterr().out
