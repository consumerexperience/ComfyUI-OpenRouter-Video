"""Lazy ComfyUI discovery entry point for the pinned Phase-6 V3 adapter."""

from typing import Any


async def comfy_entrypoint() -> Any:
    """Load the V3 extension only when ComfyUI invokes the entry point."""
    from openrouter_video.comfy.extension import comfy_entrypoint as load_extension

    return await load_extension()


__all__ = ("comfy_entrypoint",)
