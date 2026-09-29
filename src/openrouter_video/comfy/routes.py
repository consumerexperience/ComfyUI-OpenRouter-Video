"""Minimal local Comfy route backed only by the Core capability service."""

from __future__ import annotations

import threading
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Final

from openrouter_video.errors import ProductFailureError, RequestPolicyError
from openrouter_video.pricing import CostEstimateInputs, ReferenceMode
from openrouter_video.secrets import openrouter_credential_state

from . import compat
from .projection import project_model
from .runtime import get_runtime, local_runtime_health

_REGISTRY_ATTRIBUTE: Final = "_openrouter_video_registered_routes"
_LOCK_ATTRIBUTE: Final = "_openrouter_video_route_registration_lock"
_BOOTSTRAP_LOCK = threading.Lock()


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
            **compat.catalogue_health_snapshot(),
            "plugin_version": plugin_version,
            "ui_contract_version": compat.UI_CONTRACT_VERSION,
        },
        status=200,
    )


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
        "reference_mode",
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
    reference_raw = value.get("reference_mode", ReferenceMode.NONE.value)
    if not isinstance(reference_raw, str):
        raise ValueError("reference_mode is invalid")
    return CostEstimateInputs(
        model_id=model_id,
        duration=duration_raw,
        resolution=_optional_text(value.get("resolution")),
        aspect_ratio=_optional_text(value.get("aspect_ratio")),
        size=_optional_text(value.get("size")),
        generate_audio=audio,
        reference_mode=ReferenceMode(reference_raw),
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
            ("get", compat.MODEL_ROUTE, _models_handler),
            ("get", compat.UI_CAPABILITIES_ROUTE, _ui_capabilities_handler),
            ("post", compat.COST_ESTIMATE_ROUTE, _cost_estimate_handler),
        )
        for method, path, handler in routes:
            marker = (method, path)
            if marker in registered:
                continue
            getattr(server.routes, method)(path)(handler)
            registered.add(marker)


__all__ = ("register_routes",)
