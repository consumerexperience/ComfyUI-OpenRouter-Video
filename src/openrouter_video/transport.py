"""Zero-auto-retry HTTPX transport for policy-prepared OpenRouter requests."""

from __future__ import annotations

from types import TracebackType

import httpx

from openrouter_video.errors import TransportError
from openrouter_video.policy import RuntimePolicy
from openrouter_video.request_policy import (
    _PreparedOpenRouterRequest,
    _validate_prepared_request,
)

_TRANSPORT_CAPABILITY = object()


class HttpxTransport:
    """Own one managed client and move bytes without business retry semantics."""

    __slots__ = ("_client",)

    def __init__(self, client: httpx.AsyncClient, *, _capability: object) -> None:
        if _capability is not _TRANSPORT_CAPABILITY:
            raise TypeError("Use HttpxTransport.create() or HttpxTransport.for_test()")
        self._client = client

    @classmethod
    def create(cls, runtime_policy: RuntimePolicy | None = None) -> HttpxTransport:
        """Create the fixed production transport with no ambient network policy."""

        policy = runtime_policy or RuntimePolicy()
        limits = httpx.Limits(
            max_connections=policy.max_connections,
            max_keepalive_connections=policy.max_keepalive_connections,
        )
        byte_transport = httpx.AsyncHTTPTransport(
            verify=True,
            trust_env=False,
            limits=limits,
            retries=0,
        )
        client = httpx.AsyncClient(
            transport=byte_transport,
            follow_redirects=False,
            trust_env=False,
        )
        return cls(client, _capability=_TRANSPORT_CAPABILITY)

    @classmethod
    def for_test(cls, transport: httpx.AsyncBaseTransport) -> HttpxTransport:
        """Create a zero-network client around an explicit test transport."""

        client = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        )
        return cls(client, _capability=_TRANSPORT_CAPABILITY)

    async def send(self, request: _PreparedOpenRouterRequest) -> httpx.Response:
        """Send exactly one prepared request and never follow a redirect."""

        _validate_prepared_request(request)
        timeout = httpx.Timeout(
            connect=request.timeout.connect_seconds,
            write=request.timeout.write_seconds,
            read=request.timeout.read_seconds,
            pool=request.timeout.pool_seconds,
        )
        outgoing = self._client.build_request(
            request.method,
            request.url,
            headers=request._headers,
            content=request._body,
            timeout=timeout,
        )
        try:
            return await self._client.send(outgoing, follow_redirects=False)
        except httpx.HTTPError:
            raise TransportError("OpenRouter transport failed") from None

    async def aclose(self) -> None:
        """Close the shared HTTPX client."""

        await self._client.aclose()

    async def __aenter__(self) -> HttpxTransport:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        await self.aclose()


__all__ = ("HttpxTransport",)
