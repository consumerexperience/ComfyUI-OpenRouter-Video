"""Minimal local Comfy route backed only by the Core capability service."""

from __future__ import annotations

import asyncio
import threading
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Final

from openrouter_video.errors import OpenRouterHTTPError, ProductFailureError, RequestPolicyError
from openrouter_video.models import InferenceMethod, InputReferenceKind
from openrouter_video.oauth import exchange as exchange_pkce
from openrouter_video.pricing import CostEstimateInputs
from openrouter_video.secrets import (
    clear_interactive_openrouter_api_key,
    interactive_credential_status,
    openrouter_credential_source,
    openrouter_credential_state,
    pending_interactive_credential,
    set_interactive_openrouter_api_key,
)

from . import compat
from .oauth_loopback import LoopbackReceiver
from .projection import project_model
from .runtime import get_runtime, local_runtime_health

_REGISTRY_ATTRIBUTE: Final = "_openrouter_video_registered_routes"
_LOCK_ATTRIBUTE: Final = "_openrouter_video_route_registration_lock"
_BOOTSTRAP_LOCK = threading.Lock()
_oauth_receiver: LoopbackReceiver | None = None
_oauth_start_lock: asyncio.Lock | None = None


async def _models_handler(_: Any) -> Any:
    try:
        observation = await get_runtime().catalog()
    except (ProductFailureError, RequestPolicyError):
        compat.mark_catalogue_unavailable()
        return compat.json_response({"error": "model_catalog_unavailable"}, status=503)
    except Exception:
        return compat.json_response({"error": "model_catalog_internal_error"}, status=500)

    model_ids = tuple(model.model_id for model in observation.models)
    if any(
        not isinstance(model_id, str)
        or not model_id
        or model_id != model_id.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in model_id)
        for model_id in model_ids
    ):
        return compat.json_response({"error": "model_catalog_internal_error"}, status=500)
    sorted_model_ids = tuple(sorted(model_ids))
    return compat.json_response([compat.MODEL_UNRESOLVED, *sorted_model_ids], status=200)


async def _ui_capabilities_handler(_: Any) -> Any:
    try:
        observation = await get_runtime().effective_catalog()
        projected = tuple(
            project_model(model, observation.observed_at) for model in observation.models
        )
    except (ProductFailureError, RequestPolicyError):
        compat.mark_catalogue_unavailable()
        return compat.json_response({"error": "model_catalog_unavailable"}, status=503)
    except Exception:
        return compat.json_response({"error": "model_catalog_internal_error"}, status=500)
    sorted_projected = tuple(sorted(projected, key=lambda item: item.model_id))
    model_ids = tuple(item.model_id for item in sorted_projected)
    revision = compat.cache_catalogue_health(model_ids, observation.observed_at.isoformat())
    return compat.json_response(
        {
            "observed_at": observation.observed_at.isoformat(),
            "catalogue_revision": revision,
            "ui_contract_version": compat.UI_CONTRACT_VERSION,
            "models": [item.as_dict() for item in sorted_projected],
        },
        status=200,
    )


async def _health_handler(_: Any) -> Any:
    """Return pure local sanitized state; never perform upstream or paid work."""

    try:
        plugin_version = version("openrouter-video")
    except PackageNotFoundError:
        plugin_version = "0.1.0"
    return compat.json_response(
        {
            "schema_version": 1,
            "plugin_loaded": True,
            **local_runtime_health(),
            "credential_state": openrouter_credential_state(),
            "credential_source": openrouter_credential_source(),
            **compat.catalogue_health_snapshot(),
            "plugin_version": plugin_version,
            "ui_contract_version": compat.UI_CONTRACT_VERSION,
        },
        status=200,
    )


def _connection_payload() -> dict[str, object]:
    source = openrouter_credential_source()
    persistent, attention = (
        interactive_credential_status() if source != "ENVIRONMENT" else (False, False)
    )
    return {
        "state": "CONNECTED" if source != "NONE" else "DISCONNECTED",
        "source": source,
        "restart_required": False,
        "persistent": persistent,
        "needs_attention": attention,
    }


async def _connection_handler(_: Any) -> Any:
    """Return local connection state without network work or secret material."""

    return compat.json_response(_connection_payload(), status=200)


async def _connect_handler(request: Any) -> Any:
    """Validate one user-supplied key with a catalogue GET, never a paid submit."""

    if openrouter_credential_source() == "ENVIRONMENT":
        return compat.json_response(
            {"error": "environment_credential_active", "message": "OPENROUTER_API_KEY is active."},
            status=409,
        )
    try:
        body = await request.json()
        key = body.get("api_key") if isinstance(body, dict) else None
        if (
            not isinstance(key, str)
            or not key.strip()
            or len(key.strip()) > 512
            or any(ord(character) < 32 or ord(character) == 127 for character in key.strip())
        ):
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        return compat.json_response(
            {"error": "invalid_credential", "message": "Paste a valid OpenRouter API key."},
            status=400,
        )
    try:
        with pending_interactive_credential(key):
            observation = await get_runtime().validate_connection()
        set_interactive_openrouter_api_key(key)
    except ProductFailureError as exc:
        if exc.error.code.value == "API_KEY_INVALID":
            return compat.json_response(
                {"error": "invalid_credential", "message": "OpenRouter rejected this API key."},
                status=401,
            )
        return compat.json_response(
            {
                "error": "catalog_unavailable",
                "message": "OpenRouter model catalogue is temporarily unavailable.",
            },
            status=503,
        )
    except RequestPolicyError:
        if interactive_credential_status()[1]:
            return compat.json_response(
                {
                    **_connection_payload(),
                    "message": "OpenRouter connection needs attention. Reconnect to continue.",
                },
                status=503,
            )
        return compat.json_response(
            {"error": "invalid_credential", "message": "OpenRouter rejected this API key."},
            status=401,
        )
    except OpenRouterHTTPError as exc:
        return compat.json_response(
            {
                "error": "connection_rejected",
                "message": "OpenRouter could not validate this connection.",
            },
            status=401 if exc.status_code in {401, 403} else 503,
        )
    except Exception:
        return compat.json_response(
            {
                "error": "connection_unavailable",
                "message": "OpenRouter connection needs attention. Reconnect to continue.",
            },
            status=503,
        )
    return compat.json_response(
        {**_connection_payload(), "model_count": len(observation.models)}, status=200
    )


async def _disconnect_handler(_: Any) -> Any:
    """Remove persistent and session credentials; environment credentials remain active."""

    try:
        clear_interactive_openrouter_api_key()
    except RequestPolicyError:
        return compat.json_response(
            {
                **_connection_payload(),
                "message": "Stored connection could not be removed. Reconnect to continue.",
            },
            status=503,
        )
    return compat.json_response(_connection_payload(), status=200)


async def _auth_start_handler(request: Any) -> Any:
    if openrouter_credential_source() == "ENVIRONMENT":
        return compat.json_response(
            {"error": "environment_credential_active", "message": "Managed by environment"},
            status=409,
        )
    global _oauth_receiver, _oauth_start_lock

    if _oauth_start_lock is None:
        _oauth_start_lock = asyncio.Lock()
    async with _oauth_start_lock:
        if _oauth_receiver is not None:
            await _oauth_receiver.close()
        _oauth_receiver = LoopbackReceiver(_complete_oauth)
        try:
            authorization_url = await _oauth_receiver.start()
        except Exception:
            return compat.json_response(
                {
                    "error": "auth_unavailable",
                    "message": "OpenRouter sign-in could not be started.",
                },
                status=503,
            )
    return compat.json_response({"authorization_url": authorization_url}, status=200)


async def _complete_oauth(state: str, code: str) -> bool:
    """Existing exchange, uncached credential validation and storage, status only."""

    if openrouter_credential_source() == "ENVIRONMENT":
        return False
    try:
        key = await exchange_pkce(state, code)
        with pending_interactive_credential(key):
            await get_runtime().validate_connection()
        set_interactive_openrouter_api_key(key)
    except Exception:
        return False
    return True


async def _cost_estimate_handler(request: Any) -> Any:
    try:
        body = await request.json()
        inputs = _parse_estimate_inputs(body)
        result = await get_runtime().estimate_cost(inputs)
    except (TypeError, ValueError):
        return compat.json_response({"error": "invalid_estimate_request"}, status=400)
    except (ProductFailureError, RequestPolicyError):
        return compat.json_response({"error": "model_catalog_unavailable"}, status=503)
    except Exception:
        return compat.json_response({"error": "cost_estimate_internal_error"}, status=500)

    payload: dict[str, object] = {
        "availability": result.availability.value,
        "observed_at": result.observed_at.isoformat(),
        "applied_skus": result.applied_skus,
    }
    if result.estimated_cost_usd is not None:
        payload["estimated_cost_usd"] = format(result.estimated_cost_usd, "f")
    if result.provenance is not None:
        payload["provenance"] = result.provenance
    if result.reason is not None:
        payload["reason"] = result.reason
    return compat.json_response(payload, status=200)


def _parse_estimate_inputs(value: object) -> CostEstimateInputs:
    if not isinstance(value, dict):
        raise ValueError("estimate request must be an object")
    allowed = {
        "model_id",
        "duration",
        "resolution",
        "aspect_ratio",
        "size",
        "generate_audio",
        "inference_method",
        "reference_kinds",
        "reference_count",
        "source_video_present",
    }
    if set(value) - allowed:
        raise ValueError("estimate request contains unsupported fields")
    model_id = _required_text(value.get("model_id"))
    duration_raw = value.get("duration")
    if duration_raw is not None and (
        isinstance(duration_raw, bool) or not isinstance(duration_raw, int) or duration_raw <= 0
    ):
        raise ValueError("duration is invalid")
    audio = value.get("generate_audio", False)
    if not isinstance(audio, bool):
        raise ValueError("generate_audio is invalid")
    method_raw = value.get("inference_method", InferenceMethod.T2V.value)
    if not isinstance(method_raw, str):
        raise ValueError("inference_method is invalid")
    kinds_raw = value.get("reference_kinds", [])
    if not isinstance(kinds_raw, list) or any(not isinstance(item, str) for item in kinds_raw):
        raise ValueError("reference_kinds is invalid")
    count_raw = value.get("reference_count", 0)
    if isinstance(count_raw, bool) or not isinstance(count_raw, int) or count_raw < 0:
        raise ValueError("reference_count is invalid")
    source_video = value.get("source_video_present", False)
    if not isinstance(source_video, bool):
        raise ValueError("source_video_present is invalid")
    return CostEstimateInputs(
        model_id=model_id,
        duration=duration_raw,
        resolution=_optional_text(value.get("resolution")),
        aspect_ratio=_optional_text(value.get("aspect_ratio")),
        size=_optional_text(value.get("size")),
        generate_audio=audio,
        inference_method=InferenceMethod(method_raw),
        reference_kinds=tuple(InputReferenceKind(item) for item in kinds_raw),
        reference_count=count_raw,
        source_video_present=source_video,
    )


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 512:
        raise ValueError("required text is invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("required text is invalid")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _required_text(value)


def register_routes() -> None:
    """Register the route once per PromptServer without creating the Core runtime."""

    server = compat.prompt_server()
    guard = getattr(server, _LOCK_ATTRIBUTE, None)
    if guard is None:
        with _BOOTSTRAP_LOCK:
            guard = getattr(server, _LOCK_ATTRIBUTE, None)
            if guard is None:
                guard = threading.RLock()
                setattr(server, _LOCK_ATTRIBUTE, guard)
    with guard:
        registered = getattr(server, _REGISTRY_ATTRIBUTE, None)
        if registered is None:
            registered = set()
            setattr(server, _REGISTRY_ATTRIBUTE, registered)
        routes = (
            ("get", compat.HEALTH_ROUTE, _health_handler),
            ("get", compat.CONNECTION_ROUTE, _connection_handler),
            ("get", compat.MODEL_ROUTE, _models_handler),
            ("get", compat.UI_CAPABILITIES_ROUTE, _ui_capabilities_handler),
            ("post", compat.COST_ESTIMATE_ROUTE, _cost_estimate_handler),
            ("post", compat.CONNECTION_ROUTE, _connect_handler),
            ("delete", compat.CONNECTION_ROUTE, _disconnect_handler),
            ("post", compat.AUTH_START_ROUTE, _auth_start_handler),
        )
        for method, path, handler in routes:
            marker = (method, path)
            if marker in registered:
                continue
            getattr(server.routes, method)(path)(handler)
            registered.add(marker)


__all__ = ("register_routes",)
