"""Isolated S3-compatible transport; never consumes OpenRouter authentication."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from openrouter_video.local_media import run_file_worker

_transport_log_context = threading.local()


class _StorageLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # SDK debug messages contain signed URLs, headers, bodies and credentials.
        return not bool(getattr(_transport_log_context, "active", False))


def _protect_sdk_logs() -> None:
    for name in list(logging.Logger.manager.loggerDict):
        if name.startswith(("botocore", "boto3", "s3transfer", "urllib3")):
            logger = logging.getLogger(name)
            if not any(isinstance(item, _StorageLogFilter) for item in logger.filters):
                logger.addFilter(_StorageLogFilter())


STAGING_PREFIX = "openrouter-video/staging/"
SIGNED_GET_SECONDS = 24 * 60 * 60
_KEY = re.compile(r"openrouter-video/staging/[0-9a-f]{32}\.(mp4|wav)\Z")


class StorageError(RuntimeError):
    """Sanitized local configuration or storage transport error."""


@dataclass(frozen=True, slots=True, repr=False)
class StorageConfig:
    endpoint: str
    region: str
    bucket: str
    access_key: str = field(repr=False)
    secret_key: str = field(repr=False)
    session_token: str | None = field(default=None, repr=False)

    @property
    def fingerprint(self) -> str:
        values = [self.endpoint, self.region, self.bucket]
        return hashlib.sha256(json.dumps(values).encode()).hexdigest()


class StorageSecretProvider:
    """Read only explicitly named local settings; no AWS credential chain."""

    def resolve(self) -> StorageConfig:
        def read(name: str) -> str:
            return os.environ.get("OPENROUTER_VIDEO_S3_" + name, "").strip()

        config = StorageConfig(
            read("ENDPOINT"),
            read("REGION"),
            read("BUCKET"),
            read("ACCESS_KEY_ID"),
            read("SECRET_ACCESS_KEY"),
            read("SESSION_TOKEN") or None,
        )
        if not all(
            (config.endpoint, config.region, config.bucket, config.access_key, config.secret_key)
        ):
            raise StorageError("Configure local S3 endpoint, region, bucket and credentials.")
        try:
            parsed = urlsplit(config.endpoint)
            port = parsed.port
        except ValueError:
            raise StorageError("Storage endpoint is invalid.") from None
        host = parsed.hostname or ""
        if (
            (port is not None and not 1 <= port <= 65535)
            or parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise StorageError("Storage requires a canonical public HTTPS endpoint.")
        try:
            public = ipaddress.ip_address(host).is_global
        except ValueError:
            public = "." in host and not host.endswith((".local", ".internal", ".localhost"))
        if not public or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", config.bucket):
            raise StorageError("Storage endpoint or bucket is invalid.")
        return config


class MediaUploader(Protocol):
    def configuration_fingerprint(self) -> str: ...
    async def upload(self, key: str, path: Path, content_type: str) -> None: ...
    async def presign_get(self, key: str) -> str: ...
    async def delete(self, key: str) -> None: ...


class S3MediaUploader:
    """One PutObject call, SDK budget three, guarded actual sends and no redirects."""

    def __init__(self, secret_provider: StorageSecretProvider | None = None) -> None:
        self._secrets = secret_provider or StorageSecretProvider()

    def configuration_fingerprint(self) -> str:
        return self._secrets.resolve().fingerprint

    @staticmethod
    def _client(config: StorageConfig) -> Any:
        import boto3
        from botocore.config import Config

        _protect_sdk_logs()
        client = boto3.client(
            "s3",
            endpoint_url=config.endpoint,
            region_name=config.region,
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            aws_session_token=config.session_token,
            config=Config(
                signature_version="s3v4",
                connect_timeout=10,
                read_timeout=60,
                retries={"mode": "standard", "total_max_attempts": 3},
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        _protect_sdk_logs()
        return client

    def _perform(
        self, action: str, key: str, path: Path | None = None, content_type: str | None = None
    ) -> str | None:
        if not _KEY.fullmatch(key):
            raise StorageError("Storage object ownership is invalid.")
        config = self._secrets.resolve()
        _transport_log_context.active = True
        try:
            client = self._client(config)
            attempts = 0
            expected = urlsplit(config.endpoint)

            def before_send(request: Any, **_: Any) -> None:
                nonlocal attempts
                destination = urlsplit(request.url)
                if destination.netloc != expected.netloc or destination.scheme != expected.scheme:
                    raise StorageError("Storage redirect is forbidden.")
                attempts += 1
                if attempts > 3:
                    raise StorageError("Storage attempt budget exhausted.")

            def after_call(http_response: Any, **_: Any) -> None:
                if 300 <= http_response.status_code < 400:
                    raise StorageError("Storage redirect is forbidden.")

            def no_redirect(response: Any = None, **_: Any) -> None:
                if attempts >= 3 and (response is None or response[0].status_code >= 400):
                    raise StorageError("Storage attempt budget exhausted.")
                if response is not None and 300 <= response[0].status_code < 400:
                    raise StorageError("Storage redirect is forbidden.")

            client.meta.events.register_first("before-send.s3", before_send)
            client.meta.events.register_first("needs-retry.s3", no_redirect)
            client.meta.events.register_first("after-call.s3", after_call)
            try:
                if action == "upload":
                    if path is None or content_type not in {"video/mp4", "audio/wav"}:
                        raise StorageError("Storage upload input is invalid.")
                    with path.open("rb") as body:
                        client.put_object(
                            Bucket=config.bucket,
                            Key=key,
                            Body=body,
                            ContentLength=path.stat().st_size,
                            ContentType=content_type,
                        )
                elif action == "presign":
                    return str(
                        client.generate_presigned_url(
                            "get_object",
                            Params={"Bucket": config.bucket, "Key": key},
                            ExpiresIn=SIGNED_GET_SECONDS,
                            HttpMethod="GET",
                        )
                    )
                elif action == "delete":
                    client.delete_object(Bucket=config.bucket, Key=key)
                else:
                    raise StorageError("Storage operation is invalid.")
            finally:
                client.close()
        except StorageError:
            raise
        except Exception:
            raise StorageError(
                "Storage operation failed; check local configuration and access."
            ) from None
        finally:
            _transport_log_context.active = False
        return None

    async def upload(self, key: str, path: Path, content_type: str) -> None:
        await run_file_worker(self._perform, "upload", key, path, content_type)

    async def presign_get(self, key: str) -> str:
        result = await run_file_worker(self._perform, "presign", key)
        if result is None:
            raise StorageError("Storage did not produce a signed URL.")
        return result

    async def delete(self, key: str) -> None:
        await run_file_worker(self._perform, "delete", key)
