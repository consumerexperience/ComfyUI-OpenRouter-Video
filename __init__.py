"""ComfyUI discovery entry point for the Phase 3 scaffold.

The implementation intentionally exposes an empty V3 extension. Product nodes are not
part of the scaffold phase.
"""

from typing import Any


async def comfy_entrypoint() -> Any:
    """Load the empty V3 extension only when ComfyUI invokes the entry point."""
    from openrouter_video.comfy.extension import comfy_entrypoint as load_extension

    return await load_extension()


__all__ = ("comfy_entrypoint",)
