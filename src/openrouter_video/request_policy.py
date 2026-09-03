"""Origin-bound composition of authenticated OpenRouter requests."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final
from urllib.parse import quote

import httpx

from openrouter_video.app_identity import AppIdentity
from openrouter_video.errors import RequestPolicyError
from openrouter_video.policy import (
    CANONICAL_OPENROUTER_ORIGIN,
    OPENROUTER_API_PREFIX,
    Operation,
    RuntimePolicy,
    TimeoutPolicy,
)
from openrouter_video.secrets import SecretProvider

_PREPARED_CAPABILITY: Final = object()
_CATEGORY_PATTERN: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_COMMON_HEADER_NAMES: Final = frozenset(
    {
        "authorization",
        "http-referer",
        "x-openrouter-title",
        "x-openrouter-categories",
        "accept",
    }
)


@dataclass(frozen=True, slots=True)
class _PreparedOpenRouterRequest:
    """Internal transport capability produced only by ``OpenRouterRequestPolicy``."""

    operation: Operation
    method: str
    url: httpx.URL
    timeout: TimeoutPolicy
    wall_clock_seconds: float | None
    _headers: tuple[tuple[str, str], ...] = field(repr=False)
    _body: bytes | None = field(repr=False)
    _capability: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._capability is not _PREPARED_CAPABILITY:
            raise RequestPolicyError("Prepared request capability is invalid")


def _validate_canonical_destination(destination: str | httpx.URL) -> httpx.URL:
    """Return a parsed canonical OpenRouter URL or reject it before transmission."""

    try:
        url = destination if isinstance(destination, httpx.URL) else httpx.URL(destination)
    except (httpx.InvalidURL, ValueError):
        raise RequestPolicyError("OpenRouter destination is invalid") from None

    if (
        url.scheme != "https"
        or url.host != "openrouter.ai"
        or url.port not in (None, 443)
        or bool(url.userinfo)
        or bool(url.fragment)
        or not (
            url.path == OPENROUTER_API_PREFIX or url.path.startswith(f"{OPENROUTER_API_PREFIX}/")
        )
    ):
        raise RequestPolicyError("OpenRouter destination is outside canonical policy")
    return url


def _validate_identity(identity: AppIdentity) -> None:
    try:
        referer = httpx.URL(identity.referer)
    except (httpx.InvalidURL, ValueError):
        raise RequestPolicyError("Application identity is invalid") from None

    if (
        referer.scheme != "https"
        or not referer.host
        or referer.port not in (None, 443)
        or bool(referer.userinfo)
        or bool(referer.query)
        or bool(referer.fragment)
    ):
        raise RequestPolicyError("Application identity is invalid")
    if not identity.title.strip() or identity.title != identity.title.strip():
        raise RequestPolicyError("Application identity is invalid")
    if not 1 <= len(identity.categories) <= 2:
        raise RequestPolicyError("Application identity is invalid")
    if any(
        len(category) > 30 or not _CATEGORY_PATTERN.fullmatch(category)
        for category in identity.categories
    ):
        raise RequestPolicyError("Application identity is invalid")


def _encoded_job_id(job_id: str | None) -> str:
    if job_id is None or not job_id.strip():
        raise RequestPolicyError("OpenRouter job identifier is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in job_id):
        raise RequestPolicyError("OpenRouter job identifier is invalid")
    return quote(job_id, safe="-._~")


def _validate_prepared_request(request: _PreparedOpenRouterRequest) -> None:
    """Defensively revalidate an internal capability immediately before transport."""

    if not isinstance(request, _PreparedOpenRouterRequest):
        raise RequestPolicyError("Transport requires a prepared OpenRouter request")
    if request._capability is not _PREPARED_CAPABILITY:
        raise RequestPolicyError("Prepared request capability is invalid")

    _validate_canonical_destination(request.url)
    normalized_headers = {name.lower(): value for name, value in request._headers}
    names = set(normalized_headers)
    expected = set(_COMMON_HEADER_NAMES)
    policy = RuntimePolicy().for_operation(request.operation)
    if policy.is_json:
        expected.add("content-type")
    if len(request._headers) != len(expected) or names != expected or "x-title" in names:
        raise RequestPolicyError("Prepared request headers violate outbound policy")
    authorization = normalized_headers["authorization"]
    if not authorization.startswith("Bearer ") or not authorization.removeprefix("Bearer ").strip():
        raise RequestPolicyError("Prepared request headers violate outbound policy")
    if normalized_headers["accept"] != policy.accept:
        raise RequestPolicyError("Prepared request headers violate outbound policy")
    if policy.is_json and normalized_headers["content-type"] != "application/json":
        raise RequestPolicyError("Prepared request headers violate outbound policy")
    _validate_identity(
        AppIdentity(
            referer=normalized_headers["http-referer"],
            title=normalized_headers["x-openrouter-title"],
            categories=tuple(normalized_headers["x-openrouter-categories"].split(",")),
        )
    )
    if request.method != policy.method:
        raise RequestPolicyError("Prepared request method violates operation policy")
    raw_path = request.url.raw_path.decode("ascii")
    if request.operation is Operation.DISCOVERY:
        route_is_valid = raw_path == "/api/v1/videos/models"
    elif request.operation is Operation.SUBMIT:
        route_is_valid = raw_path == "/api/v1/videos"
    elif request.operation is Operation.POLL:
        route_is_valid = re.fullmatch(r"/api/v1/videos/[^/?]+", raw_path) is not None
    else:
        route_is_valid = (
            re.fullmatch(r"/api/v1/videos/[^/?]+/content\?index=0", raw_path) is not None
        )
    if not route_is_valid:
        raise RequestPolicyError("Prepared request path violates operation policy")


class OpenRouterRequestPolicy:
    """The sole owner of OpenRouter destination and security-header composition."""

    __slots__ = ("_identity", "_runtime_policy", "_secret_provider")

    def __init__(
        self,
        *,
        identity: AppIdentity,
        secret_provider: SecretProvider,
        runtime_policy: RuntimePolicy | None = None,
    ) -> None:
        self._identity = identity
        self._secret_provider = secret_provider
        self._runtime_policy = runtime_policy or RuntimePolicy()

    def prepare(
        self,
        operation: Operation,
        *,
        job_id: str | None = None,
        json_body: Mapping[str, object] | None = None,
    ) -> _PreparedOpenRouterRequest:
        """Build one canonical request without sending it or applying retries."""

        operation_policy = self._runtime_policy.for_operation(operation)
        destination = self._destination(operation, job_id=job_id)
        canonical_url = _validate_canonical_destination(destination)
        _validate_identity(self._identity)
        body = self._body(operation, json_body=json_body)

        credential = self._secret_provider.get_openrouter_api_key()
        if not credential.strip():
            raise RequestPolicyError("OpenRouter API credential is not configured")

        headers = [
            ("Authorization", f"Bearer {credential}"),
            ("HTTP-Referer", self._identity.referer),
            ("X-OpenRouter-Title", self._identity.title),
            ("X-OpenRouter-Categories", ",".join(self._identity.categories)),
            ("Accept", operation_policy.accept),
        ]
        if operation_policy.is_json:
            headers.append(("Content-Type", "application/json"))

        request = _PreparedOpenRouterRequest(
            operation=operation,
            method=operation_policy.method,
            url=canonical_url,
            timeout=operation_policy.timeout,
            wall_clock_seconds=operation_policy.timeout.wall_clock_seconds,
            _headers=tuple(headers),
            _body=body,
            _capability=_PREPARED_CAPABILITY,
        )
        _validate_prepared_request(request)
        return request

    def _destination(self, operation: Operation, *, job_id: str | None) -> str:
        policy = self._runtime_policy.for_operation(operation)
        if operation in (Operation.POLL, Operation.CONTENT):
            path = policy.path_template.format(job_id=_encoded_job_id(job_id))
        else:
            if job_id is not None:
                raise RequestPolicyError("Operation does not accept a job identifier")
            path = policy.path_template
        return f"{CANONICAL_OPENROUTER_ORIGIN}{path}"

    @staticmethod
    def _body(operation: Operation, *, json_body: Mapping[str, object] | None) -> bytes | None:
        if operation is Operation.SUBMIT:
            if json_body is None:
                raise RequestPolicyError("Submit operation requires a JSON body")
            try:
                return json.dumps(json_body, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            except (TypeError, ValueError):
                raise RequestPolicyError("Submit JSON body is not serializable") from None
        if json_body is not None:
            raise RequestPolicyError("Operation does not accept a JSON body")
        return None


__all__ = ("OpenRouterRequestPolicy",)
