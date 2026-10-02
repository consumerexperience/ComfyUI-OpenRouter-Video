"""Fail-closed compatibility facade for the pinned ComfyUI V3 host."""

from __future__ import annotations

import threading
from hashlib import sha256
from pathlib import Path
from typing import Any, Final, NoReturn

from comfy_api.v0_0_2 import IO, ComfyAPI, ComfyExtension, InputImpl, Types

from openrouter_video.execution_hooks import ExecutionPhase

EXPECTED_API_VERSION: Final = "0.0.2"
MODEL_ROUTE: Final = "/openrouter-video/v1/models"
UI_CAPABILITIES_ROUTE: Final = "/openrouter-video/v1/ui-capabilities"
HEALTH_ROUTE: Final = "/openrouter-video/v1/health"
COST_ESTIMATE_ROUTE: Final = "/openrouter-video/v1/cost-estimate"
UI_CONTRACT_VERSION: Final = 4
MODEL_UNRESOLVED: Final = "SELECT MODEL"
AUTO_MODEL_DEFAULT: Final = "AUTO / MODEL DEFAULT"
_CUSTOM_FACTORY = getattr(IO, "Custom", None)
INPUT_REFERENCE_IO: Any = (
    _CUSTOM_FACTORY("OPENROUTER_VIDEO_INPUT_REFERENCE") if _CUSTOM_FACTORY is not None else None
)
IMAGE_OR_REFERENCE_IO: Any = (
    _CUSTOM_FACTORY("IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE")
    if _CUSTOM_FACTORY is not None
    else None
)
MEDIA_OR_REFERENCE_IO: Any = (
    _CUSTOM_FACTORY("IMAGE,VIDEO,AUDIO,OPENROUTER_VIDEO_INPUT_REFERENCE")
    if _CUSTOM_FACTORY is not None
    else None
)
VIDEO_OR_REFERENCE_IO: Any = (
    _CUSTOM_FACTORY("VIDEO,OPENROUTER_VIDEO_INPUT_REFERENCE")
    if _CUSTOM_FACTORY is not None
    else None
)
INPUT_REFERENCE_COLLECTION_IO: Any = (
    _CUSTOM_FACTORY("OPENROUTER_VIDEO_INPUT_REFERENCES") if _CUSTOM_FACTORY is not None else None
)
_PHASE_ORDINAL: Final = {
    ExecutionPhase.VALIDATING: 1,
    ExecutionPhase.SUBMITTING: 2,
    ExecutionPhase.ACCEPTED: 3,
    ExecutionPhase.POLLING: 4,
    ExecutionPhase.DOWNLOADING: 5,
    ExecutionPhase.NATIVE_VIDEO: 6,
    ExecutionPhase.DONE: 7,
}
_CACHE_TOKEN_LOCK = threading.Lock()
_cache_token = 0
_CATALOGUE_HEALTH_LOCK = threading.Lock()
_catalogue_health: dict[str, object] = {
    "catalogue_state": "UNKNOWN",
    "catalogue_model_count": 0,
    "catalogue_revision": None,
}


class UnsupportedComfyError(RuntimeError):
    """The host does not provide the numbered API contract used by Phase 6."""


def validate_host_api() -> None:
    """Validate the version marker and capabilities exposed by the numbered API."""

    version = getattr(ComfyAPI, "VERSION", None)
    required = (
        getattr(IO, "RemoteOptions", None),
        getattr(getattr(IO, "Combo", None), "Input", None),
        getattr(getattr(IO, "Int", None), "Input", None),
        getattr(IO, "ControlAfterGenerate", None),
        getattr(IO, "NumberDisplay", None),
        getattr(getattr(IO, "Video", None), "Output", None),
        getattr(getattr(IO, "Autogrow", None), "Input", None),
        getattr(IO, "Custom", None),
        INPUT_REFERENCE_IO,
        IMAGE_OR_REFERENCE_IO,
        MEDIA_OR_REFERENCE_IO,
        VIDEO_OR_REFERENCE_IO,
        INPUT_REFERENCE_COLLECTION_IO,
        getattr(InputImpl, "VideoFromFile", None),
    )
    if version != EXPECTED_API_VERSION or any(item is None for item in required):
        raise UnsupportedComfyError(
            "OpenRouter Video requires the pinned ComfyUI v0_0_2 adapter contract."
        )


def model_input() -> Any:
    """Build a sentinel-only combo owned by the frontend catalogue controller."""

    validate_host_api()
    return IO.Combo.Input(
        "model",
        options=[MODEL_UNRESOLVED],
        default=MODEL_UNRESOLVED,
        tooltip="Select a current OpenRouter video model. No model is selected by default.",
    )


def cache_catalogue_health(model_ids: tuple[str, ...], observed_at: str) -> str:
    """Record a sanitized local catalogue snapshot without upstream work."""

    manifest = f"{observed_at}\n" + "\n".join(sorted(model_ids))
    revision = sha256(manifest.encode("utf-8")).hexdigest()
    with _CATALOGUE_HEALTH_LOCK:
        _catalogue_health.update(
            catalogue_state="FRESH" if model_ids else "EMPTY",
            catalogue_model_count=len(model_ids),
            catalogue_revision=revision,
        )
    return revision


def mark_catalogue_unavailable() -> None:
    with _CATALOGUE_HEALTH_LOCK:
        _catalogue_health["catalogue_state"] = "UNAVAILABLE"


def catalogue_health_snapshot() -> dict[str, object]:
    with _CATALOGUE_HEALTH_LOCK:
        return dict(_catalogue_health)


def next_cache_token() -> int:
    """Return a JSON-safe process-local token for the pinned cache regression."""

    global _cache_token
    with _CACHE_TOKEN_LOCK:
        _cache_token += 1
        return _cache_token


def state_database_path() -> Path:
    """Return the Comfy-owned per-user durable state path."""

    import folder_paths

    return Path(folder_paths.get_user_directory()) / "openrouter-video" / "state" / "jobs.sqlite3"


def output_directory() -> Path:
    """Return the Comfy-owned adapter output directory."""

    import folder_paths

    return Path(folder_paths.get_output_directory()) / "openrouter-video"


def host_interrupted() -> bool:
    """Read the pinned host's cooperative interruption flag."""

    from comfy.model_management import processing_interrupted

    return bool(processing_interrupted())


def current_node_id(node_class: type[Any]) -> str | None:
    """Read the numbered V3 hidden node id for progress presentation."""

    hidden = getattr(node_class, "hidden", None)
    node_id = getattr(hidden, "unique_id", None)
    return str(node_id) if node_id is not None else None


async def report_phase(phase: ExecutionPhase, node_id: str | None) -> None:
    """Report discrete local stages through the pinned first-party progress API."""

    if node_id is None:
        return
    try:
        await ComfyAPI().execution.set_progress(_PHASE_ORDINAL[phase], len(_PHASE_ORDINAL), node_id)
    except Exception:
        return


def raise_host_interrupt() -> NoReturn:
    """Translate the Core's cooperative signal into the host interruption type."""

    from comfy.model_management import InterruptProcessingException

    raise InterruptProcessingException


def video_from_file(path: Path) -> Any:
    """Construct the pinned native file-backed VIDEO implementation."""

    validate_host_api()
    return InputImpl.VideoFromFile(str(path))


def prompt_server() -> Any:
    """Return the active host server without importing it outside this facade."""

    from server import PromptServer

    if PromptServer.instance is None:
        raise UnsupportedComfyError(
            "ComfyUI PromptServer is unavailable during route registration."
        )
    return PromptServer.instance


def json_response(payload: object, *, status: int) -> Any:
    """Create a host-provided JSON response with deterministic cache behavior."""

    from aiohttp import web

    return web.json_response(payload, status=status, headers={"Cache-Control": "no-store"})


__all__ = (
    "ComfyExtension",
    "Types",
    "AUTO_MODEL_DEFAULT",
    "EXPECTED_API_VERSION",
    "IO",
    "INPUT_REFERENCE_COLLECTION_IO",
    "INPUT_REFERENCE_IO",
    "IMAGE_OR_REFERENCE_IO",
    "MEDIA_OR_REFERENCE_IO",
    "VIDEO_OR_REFERENCE_IO",
    "COST_ESTIMATE_ROUTE",
    "HEALTH_ROUTE",
    "MODEL_ROUTE",
    "MODEL_UNRESOLVED",
    "UI_CAPABILITIES_ROUTE",
    "UI_CONTRACT_VERSION",
    "UnsupportedComfyError",
    "cache_catalogue_health",
    "catalogue_health_snapshot",
    "current_node_id",
    "host_interrupted",
    "json_response",
    "mark_catalogue_unavailable",
    "model_input",
    "next_cache_token",
    "output_directory",
    "prompt_server",
    "raise_host_interrupt",
    "report_phase",
    "state_database_path",
    "validate_host_api",
    "video_from_file",
)
