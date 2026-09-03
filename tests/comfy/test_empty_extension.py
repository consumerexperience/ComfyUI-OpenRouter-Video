"""Static checks for the deliberately empty ComfyUI entry seam."""

from pathlib import Path


def test_extension_declares_no_product_nodes() -> None:
    extension = (
        Path(__file__).parents[2] / "src" / "openrouter_video" / "comfy" / "extension.py"
    ).read_text(encoding="utf-8")
    assert "return []" in extension
    assert "Generate" not in extension
    assert "Resume" not in extension
