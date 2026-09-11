"""Minimal local Comfy route backed only by the Core capability service."""

from __future__ import annotations

import threading
from typing import Any, Final

from openrouter_video.errors import ProductFailureError, RequestPolicyError

from . import compat
from .runtime import get_runtime

_REGISTRY_ATTRIBUTE: Final = "_openrouter_video_registered_routes"
_LOCK_ATTRIBUTE: Final = "_openrouter_video_route_registration_lock"
_BOOTSTRAP_LOCK = threading.Lock()


async def _models_handler(_: Any) -> Any:
    try:
        observation = await get_runtime().catalog()
    except (ProductFailureError, RequestPolicyError):
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
    return compat.json_response(sorted(model_ids), status=200)


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
        if compat.MODEL_ROUTE in registered:
            return
        server.routes.get(compat.MODEL_ROUTE)(_models_handler)
        registered.add(compat.MODEL_ROUTE)


__all__ = ("register_routes",)
