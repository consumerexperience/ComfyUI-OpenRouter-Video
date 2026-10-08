"""Default selector, manifest semantics, and no-fallback Golden Pack tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.fixtures.golden_pack import (
    DEFAULT_FIXTURES_ROOT,
    MATERIALIZATION_COMMAND,
    GoldenPackError,
    GoldenPackIntegrityError,
    load_default_pack,
    load_manifest,
)


def test_default_selector_resolves_to_multimodal_pack_manifest() -> None:
    pack = load_default_pack()
    assert pack.selector_path == DEFAULT_FIXTURES_ROOT / "default_golden_pack.json"
    assert pack.manifest_path == (
        DEFAULT_FIXTURES_ROOT / "higgsfield_car_multimodal_v1" / "manifest.json"
    )
    assert pack.pack_id == "higgsfield-car-golden-multimodal-v1"
    assert load_manifest() == pack.manifest
    assert pack.manifest_path.parts[-5:-2] == ("tests", "live", "fixtures")


def test_manifest_drives_canonical_order_roles_and_transport_mapping() -> None:
    pack = load_default_pack()
    assert [item["type"] for item in pack.canonical_references] == [
        "IMAGE",
        "IMAGE",
        "VIDEO",
        "AUDIO",
    ]
    assert [item["local_filename"] for item in pack.canonical_references] == [
        "car_sheet.png",
        "loc_street_main.png",
        "Car_Chasing.mp4",
        "Passing_car_urban_ambience.wav",
    ]
    assert "video_playblast" in pack.semantic_roles["car_chasing_playblast"]
    assert "audio_reference" in pack.semantic_roles["passing_car_urban_ambience"]
    assert pack.transport_mapping["car_chasing_playblast"]["wire_type"] == "video_url"
    assert pack.transport_mapping["passing_car_urban_ambience"]["wire_type"] == "audio_url"
    assert pack.manifest["paid_generation"]["post_count"] == 0


def test_missing_binaries_report_materialization_required_without_fallback(
    tmp_path: Path,
) -> None:
    source_root = DEFAULT_FIXTURES_ROOT
    shutil.copy2(source_root / "default_golden_pack.json", tmp_path / "default_golden_pack.json")
    pack_name = "higgsfield_car_multimodal_v1"
    destination = tmp_path / pack_name
    (destination / "checks").mkdir(parents=True)
    shutil.copy2(source_root / pack_name / "manifest.json", destination / "manifest.json")
    shutil.copy2(
        source_root / pack_name / "checks" / "duplicate-reference-regression.json",
        destination / "checks" / "duplicate-reference-regression.json",
    )

    pack = load_default_pack(fixtures_root=tmp_path)
    verification = pack.verify_local_assets()
    assert pack.pack_id == "higgsfield-car-golden-multimodal-v1"
    assert verification.state == "MATERIALIZATION_REQUIRED"
    assert set(verification.missing_asset_ids) == {
        asset["asset_id"] for asset in pack.manifest["assets"]
    }
    assert MATERIALIZATION_COMMAND == "python scripts/materialize_higgsfield_multimodal_pack.py"


def test_existing_but_changed_asset_fails_integrity_check(tmp_path: Path) -> None:
    source_root = DEFAULT_FIXTURES_ROOT
    shutil.copy2(source_root / "default_golden_pack.json", tmp_path / "default_golden_pack.json")
    pack_name = "higgsfield_car_multimodal_v1"
    destination = tmp_path / pack_name
    (destination / "checks").mkdir(parents=True)
    shutil.copy2(source_root / pack_name / "manifest.json", destination / "manifest.json")
    shutil.copy2(
        source_root / pack_name / "checks" / "duplicate-reference-regression.json",
        destination / "checks" / "duplicate-reference-regression.json",
    )
    asset_path = destination / "assets" / "car_sheet.png"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"tampered")

    pack = load_default_pack(fixtures_root=tmp_path)
    with pytest.raises(GoldenPackIntegrityError, match="integrity mismatch"):
        pack.verify_local_assets()


def test_selector_does_not_fallback_or_allow_arbitrary_pack_names() -> None:
    with pytest.raises(GoldenPackError, match="Unsupported Golden Pack selector"):
        load_default_pack(selector="production")


def test_golden_pack_registry_stays_outside_production_defaults() -> None:
    root = Path(__file__).resolve().parents[2]
    protected_paths = (
        root / "src/openrouter_video/comfy/runtime.py",
        root / "src/openrouter_video/capabilities.py",
        root / "src/openrouter_video/capability_overlays.py",
        root / "src/openrouter_video/comfy/nodes.py",
    )
    for path in protected_paths:
        source = path.read_text(encoding="utf-8").casefold()
        assert "higgsfield_car_multimodal_v1" not in source
        assert "default_golden_pack" not in source
