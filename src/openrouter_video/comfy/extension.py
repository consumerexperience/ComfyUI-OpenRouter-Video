"""Empty V3 extension used only to validate Phase 3 ComfyUI discovery."""

from comfy_api.v0_0_2 import ComfyExtension


class ScaffoldExtension(ComfyExtension):
    """A deliberately empty extension: Phase 3 exports no product nodes."""

    async def get_node_list(self) -> list[type]:
        """Return no nodes until the Comfy adapter implementation phase."""
        return []


async def comfy_entrypoint() -> ScaffoldExtension:
    """Return the import-safe empty scaffold extension."""
    return ScaffoldExtension()


__all__ = ("comfy_entrypoint",)
