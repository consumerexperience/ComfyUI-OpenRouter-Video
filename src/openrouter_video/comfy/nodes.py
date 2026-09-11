"""The two public Phase-6 ComfyUI V3 adapter nodes."""

from __future__ import annotations

from openrouter_video.application import OperationInterrupted
from openrouter_video.models import (
    FrameReference,
    FrameType,
    GenerationRequest,
    GenerationResult,
    ProductErrorCode,
)

from . import compat
from .runtime import get_runtime
from .video import VideoBridgeError, to_native_video


class AdapterExecutionError(RuntimeError):
    """A sanitized user-facing adapter failure."""


def _optional_text(value: str) -> str | None:
    normalized = value.strip()
    return normalized or None


def _duration(value: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AdapterExecutionError(
            "UNSUPPORTED_PARAMETER: duration must be zero or a positive integer."
        )
    return value or None


def _seed(value: str) -> int | None:
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return int(normalized, 10)
    except ValueError:
        raise AdapterExecutionError("UNSUPPORTED_PARAMETER: seed must be an integer.") from None


def _safe_job_id(value: str | None) -> str | None:
    if value is None or len(value) > 512:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    return value


def _raise_product_error(result: GenerationResult) -> None:
    error = result.error
    if error is None:
        return
    message = f"{error.code.value}: {error.message}"
    job_id = _safe_job_id(result.job_id)
    if job_id is not None:
        message += f" Job ID: {job_id}."
    if error.code is ProductErrorCode.SUBMISSION_UNKNOWN:
        message += " Do not run Generate automatically as recovery."
    raise AdapterExecutionError(message)


def _node_output(result: GenerationResult) -> object:
    _raise_product_error(result)
    if result.artifact is None:
        raise AdapterExecutionError(
            "INVALID_VIDEO_RESPONSE: no durable video artifact is available."
        )
    try:
        video = to_native_video(result.artifact)
    except VideoBridgeError as exc:
        raise AdapterExecutionError(str(exc)) from None
    cost = format(result.actual_cost_usd, "f") if result.actual_cost_usd is not None else ""
    return compat.IO.NodeOutput(
        video,
        result.job_id or "",
        result.model or "",
        cost,
        result.state.value,
    )


def _outputs() -> list[object]:
    return [
        compat.IO.Video.Output("VIDEO"),
        compat.IO.String.Output("JOB_ID"),
        compat.IO.String.Output("MODEL"),
        compat.IO.String.Output("ACTUAL_COST_USD"),
        compat.IO.String.Output("STATUS"),
    ]


class OpenRouterVideoGenerate(compat.IO.ComfyNode):
    """Map one intentional queue execution to one Core Generate operation."""

    @classmethod
    def define_schema(cls) -> object:
        return compat.IO.Schema(
            node_id="OpenRouterVideoGenerate",
            display_name="OpenRouter Video Generate",
            category="OpenRouter/Video",
            not_idempotent=True,
            inputs=[
                compat.model_input(),
                compat.IO.String.Input("prompt", default="", multiline=True),
                compat.IO.Int.Input("duration", default=0, min=0, step=1, advanced=True),
                compat.IO.String.Input("resolution", default="", advanced=True),
                compat.IO.String.Input("aspect_ratio", default="", advanced=True),
                compat.IO.String.Input("size", default="", advanced=True),
                compat.IO.String.Input("seed", default="", advanced=True),
                compat.IO.Boolean.Input("generate_audio", default=False, advanced=True),
                compat.IO.String.Input("first_frame_url", default="", advanced=True),
                compat.IO.String.Input("last_frame_url", default="", advanced=True),
            ],
            outputs=_outputs(),
            hidden=[compat.IO.Hidden.unique_id],
        )

    @classmethod
    def fingerprint_inputs(cls, **_: object) -> int:
        """Work around the proven pinned PromptExecutor cross-queue cache regression."""

        return compat.next_cache_token()

    @classmethod
    async def execute(
        cls,
        model: str,
        prompt: str,
        duration: int = 0,
        resolution: str = "",
        aspect_ratio: str = "",
        size: str = "",
        seed: str = "",
        generate_audio: bool = False,
        first_frame_url: str = "",
        last_frame_url: str = "",
    ) -> object:
        first = _optional_text(first_frame_url)
        last = _optional_text(last_frame_url)
        request = GenerationRequest(
            model=model.strip(),
            prompt=prompt,
            duration=_duration(duration),
            resolution=_optional_text(resolution),
            aspect_ratio=_optional_text(aspect_ratio),
            size=_optional_text(size),
            seed=_seed(seed),
            generate_audio=generate_audio,
            first_frame=FrameReference(FrameType.FIRST, first) if first is not None else None,
            last_frame=FrameReference(FrameType.LAST, last) if last is not None else None,
        )
        try:
            result = await get_runtime().generate(request, compat.current_node_id(cls))
        except OperationInterrupted:
            compat.raise_host_interrupt()
        return _node_output(result)


class OpenRouterVideoResume(compat.IO.ComfyNode):
    """Observe and download an existing job without a submit capability."""

    @classmethod
    def define_schema(cls) -> object:
        return compat.IO.Schema(
            node_id="OpenRouterVideoResume",
            display_name="OpenRouter Video Resume",
            category="OpenRouter/Video",
            not_idempotent=True,
            inputs=[compat.IO.String.Input("job_id", default="")],
            outputs=_outputs(),
            hidden=[compat.IO.Hidden.unique_id],
        )

    @classmethod
    def fingerprint_inputs(cls, **_: object) -> int:
        """Prevent stale durable observation output across separate Queue actions."""

        return compat.next_cache_token()

    @classmethod
    async def execute(cls, job_id: str) -> object:
        normalized = job_id.strip()
        if not normalized:
            raise AdapterExecutionError("JOB_NOT_FOUND: job_id must not be empty.")
        try:
            result = await get_runtime().resume(normalized, compat.current_node_id(cls))
        except OperationInterrupted:
            compat.raise_host_interrupt()
        return _node_output(result)


__all__ = (
    "AdapterExecutionError",
    "OpenRouterVideoGenerate",
    "OpenRouterVideoResume",
)
