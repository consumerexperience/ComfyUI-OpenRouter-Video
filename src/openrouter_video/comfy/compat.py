"""Fail-closed compatibility facade for the pinned ComfyUI V3 host."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Final, NoReturn

from comfy_api.v0_0_2 import IO, ComfyAPI, ComfyExtension, InputImpl

from openrouter_video.execution_hooks import ExecutionPhase

EXPECTED_API_VERSION: Final = "0.0.2"
MODEL_ROUTE: Final = "/openrouter-video/v1/models"
_PHASE_ORDINAL: Final = {
    ExecutionPhase.VALIDATING: 1,
    ExecutionPhase.SUBMITTING: 2,
    ExecutionPhase.ACCEPTED: 3,
    ExecutionPhase.POLLING: 4,
    ExecutionPhase.DOWNLOADING: 5,
    ExecutionPhase.DONE: 6,
}
_CACHE_TOKEN_LOCK = threading.Lock()
_cache_token = 0


class UnsupportedComfyError(RuntimeError):
    """The host does not provide the numbered API contract used by Phase 6."""


def validate_host_api() -> None:
    """Validate the version marker and capabilities exposed by the numbered API."""

    version = getattr(ComfyAPI, "VERSION", None)
    required = (
        getattr(IO, "RemoteOptions", None),
        getattr(getattr(IO, "Combo", None), "Input", None),
        getattr(getattr(IO, "Video", None), "Output", None),
        getattr(InputImpl, "VideoFromFile", None),
    )
    if version != EXPECTED_API_VERSION or any(item is None for item in required):
        raise UnsupportedComfyError(
            "OpenRouter Video requires the pinned ComfyUI v0_0_2 adapter contract."
        )


def model_input() -> Any:
    """Build the pinned remote-backed model combo without a static catalog."""

    validate_host_api()
    remote = IO.RemoteOptions(route=MODEL_ROUTE, refresh_button=True)
    return IO.Combo.Input("model", options=[], remote=remote)


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
    await ComfyAPI().execution.set_progress(_PHASE_ORDINAL[phase], len(_PHASE_ORDINAL), node_id)


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
    "EXPECTED_API_VERSION",
    "IO",
    "MODEL_ROUTE",
    "UnsupportedComfyError",
    "current_node_id",
    "host_interrupted",
    "json_response",
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
