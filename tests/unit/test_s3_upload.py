"""Real botocore HTTP sends against a loopback fixture, never an external storage."""

from __future__ import annotations

import asyncio
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from openrouter_video.s3_upload import (
    S3MediaUploader,
    StorageConfig,
    StorageError,
    StorageSecretProvider,
)

KEY = "openrouter-video/staging/" + "a" * 32 + ".mp4"


class Secrets(StorageSecretProvider):
    def __init__(self, endpoint: str) -> None:
        self.config = StorageConfig(
            endpoint, "auto", "fixture-bucket", "storage-key-canary", "storage-secret-canary"
        )

    def resolve(self) -> StorageConfig:
        return self.config


@pytest.mark.parametrize(
    "statuses,expected", [([500, 500, 500], 3), ([500, 200], 2), ([403], 1), ([302], 1)]
)
def test_actual_http_put_budget(
    tmp_path: Path, statuses: list[int], expected: int, caplog: pytest.LogCaptureFixture
) -> None:
    seen: list[tuple[str, dict[str, str]]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self) -> None:
            self.rfile.read(int(self.headers["Content-Length"]))
            seen.append((self.path, dict(self.headers)))
            status = statuses[min(len(seen) - 1, len(statuses) - 1)]
            self.send_response(status)
            self.send_header("Content-Length", "0")
            if status == 302:
                self.send_header("Location", "/redirect-trap")
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    endpoint = "http://127.0.0.1:" + str(server.server_port)
    uploader = S3MediaUploader(Secrets(endpoint))  # Test-only provider, production requires HTTPS.
    path = tmp_path / "closed.mp4"
    path.write_bytes(b"fixture-media-canary")
    caplog.set_level(logging.DEBUG)
    try:
        if statuses[-1] == 200:
            asyncio.run(uploader.upload(KEY, path, "video/mp4"))
        else:
            with pytest.raises(StorageError) as error:
                asyncio.run(uploader.upload(KEY, path, "video/mp4"))
            assert "canary" not in str(error.value)
        assert len(seen) == expected
        assert {item[0] for item in seen} == {"/fixture-bucket/" + KEY}
        for _, headers in seen:
            assert headers["Authorization"].startswith("AWS4-HMAC-SHA256")
            assert (
                "HTTP-Referer" not in headers
                and "X-Title" not in headers
                and "X-OpenRouter-Categories" not in headers
            )
        assert all(
            canary not in caplog.text
            for canary in ["storage-key-canary", "storage-secret-canary", "fixture-media-canary"]
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_fourth_send_blocked_even_if_sdk_retry_handler_is_overridden(tmp_path: Path) -> None:
    sends: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self) -> None:
            self.rfile.read(int(self.headers["Content-Length"]))
            sends.append(self.path)
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            pass

    class ForcedRetryUploader(S3MediaUploader):
        @staticmethod
        def _client(config: StorageConfig) -> Any:
            client = S3MediaUploader._client(config)
            client.meta.events.register_first("needs-retry.s3.PutObject", lambda **_: 0)
            return client

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    path = tmp_path / "fixture.mp4"
    path.write_bytes(b"fixture")
    try:
        uploader = ForcedRetryUploader(Secrets(f"http://127.0.0.1:{server.server_port}"))
        with pytest.raises(StorageError, match="budget exhausted"):
            asyncio.run(uploader.upload(KEY, path, "video/mp4"))
        assert len(sends) == 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_presign_lifetime_and_explicit_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ambient-aws-canary")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-key-canary")
    uploader = S3MediaUploader(Secrets("https://storage.example.test"))
    url = asyncio.run(uploader.presign_get(KEY))
    query = parse_qs(urlsplit(url).query)
    assert query["X-Amz-Expires"] == ["86400"]
    assert query["X-Amz-SignedHeaders"] == ["host"]
    assert query["X-Amz-Credential"][0].startswith("storage-key-canary/")
    assert "ambient-aws-canary" not in url and "openrouter-key-canary" not in url


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://storage.example.test",
        "https://127.0.0.1",
        "https://user:password@storage.example.test",
        "https://storage.example.test/path",
        "https://storage.example.test?private=canary",
        "https://storage.example.test:wrong",
    ],
)
def test_invalid_configuration_sanitized(monkeypatch: pytest.MonkeyPatch, endpoint: str) -> None:
    for name, value in {
        "ENDPOINT": endpoint,
        "REGION": "auto",
        "BUCKET": "fixture-bucket",
        "ACCESS_KEY_ID": "key",
        "SECRET_ACCESS_KEY": "secret",
    }.items():
        monkeypatch.setenv("OPENROUTER_VIDEO_S3_" + name, value)
    with pytest.raises(StorageError) as error:
        StorageSecretProvider().resolve()
    assert endpoint not in str(error.value)
