from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "web" / "openrouter_video.js"


def test_frontend_helper_is_projection_only_and_model_agnostic() -> None:
    text = HELPER.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "/openrouter-video/v1/ui-capabilities" in text
    assert "/openrouter-video/v1/cost-estimate" in text
    assert "const UI_CONTRACT_VERSION = 4" in text
    assert "FRONTEND/BACKEND CONTRACT MISMATCH" in text
    assert "CATALOGUE EMPTY — NO SELECTABLE MODELS" in text
    assert "estimated_cost_usd" in text
    assert "pricing_skus" not in text
    assert "per-video-second" not in text
    assert "bytedance/" not in lowered
    assert "seedance" not in lowered
    assert "google/" not in lowered
    assert "authorization" not in lowered
    assert "api_key" not in lowered
    assert "prompt" not in lowered


def test_frontend_helper_keeps_unresolved_and_auto_semantics_local() -> None:
    text = HELPER.read_text(encoding="utf-8")

    assert 'const SELECT_MODEL = "SELECT MODEL"' in text
    assert 'const AUTO = "AUTO / MODEL DEFAULT"' in text
    assert "canonicalModel(node)" in text
    assert "getOptionLabel" in text
    assert 'result.availability === "AVAILABLE"' in text
    assert "ESTIMATE UNAVAILABLE" in text
    assert "migratePhase8Values" in text
    assert "Number(seed.value)" in text
    assert 'return "image"' in text
    assert 'return "video"' in text
    assert 'return "audio"' in text
    assert "switchWouldOrphan" in text
    assert "mixed_image_video_references" not in text
    assert "Core" not in text  # no attempt to reimplement validator semantics
