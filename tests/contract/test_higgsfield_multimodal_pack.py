"""Zero-cost contract and byte-integrity checks for the multimodal Golden Pack."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from tests.fixtures.golden_pack import MATERIALIZATION_COMMAND, load_default_pack

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK = load_default_pack()


def load_json(relative_path: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((PACK.pack_root / relative_path).read_text(encoding="utf-8")),
    )


def by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {asset["asset_id"]: asset for asset in manifest["assets"]}


def test_pack_materially_contains_image_video_and_audio() -> None:
    manifest = PACK.manifest
    assets = manifest["assets"]
    present_types = {asset["type"] for asset in assets}
    assert {"IMAGE", "VIDEO", "AUDIO"} <= present_types
    for asset in assets:
        assert asset["modified"] is False
        assert asset["roles"]
        assert asset["transport"]["upstream_role"]
        assert asset["transport"]["wire_type"]


def test_materialized_binary_hashes_match_manifest_or_request_materialization() -> None:
    report = PACK.verify_local_assets()
    if not report.ready:
        pytest.skip(
            "MATERIALIZATION_REQUIRED: run "
            f"{MATERIALIZATION_COMMAND}; missing={report.missing_asset_ids}"
        )
    assert set(report.checked_asset_ids) == {asset["asset_id"] for asset in PACK.manifest["assets"]}


def test_video_playblast_and_audio_reference_roles_exist() -> None:
    assets = by_id(load_json("manifest.json"))
    video = assets["car_chasing_playblast"]
    audio = assets["passing_car_urban_ambience"]
    assert video["type"] == "VIDEO"
    assert "video_playblast" in video["roles"]
    assert {
        "video_control",
        "video_camera",
        "video_motion",
        "video_timing",
        "video_environment",
    } <= set(video["roles"])
    assert video["transport"]["upstream_role"] == "video_reference"
    assert audio["type"] == "AUDIO"
    assert {"audio_reference", "audio_timing", "audio_ambience"} <= set(audio["roles"])
    assert audio["transport"]["upstream_role"] == "audio_reference"


def test_canonical_mmr2v_order_is_image_then_video_then_audio() -> None:
    manifest = load_json("manifest.json")
    assert manifest["generation_target_seconds"] == 5
    assert [(entry["type"], entry["asset_id"]) for entry in manifest["canonical_mmr2v_order"]] == [
        ("IMAGE", "car_sheet"),
        ("IMAGE", "street_environment"),
        ("VIDEO", "car_chasing_playblast"),
        ("AUDIO", "passing_car_urban_ambience"),
    ]


def test_prior_image_assets_remain_byte_identical() -> None:
    report = PACK.verify_local_assets()
    if not report.ready:
        pytest.skip(
            "MATERIALIZATION_REQUIRED: run "
            f"{MATERIALIZATION_COMMAND}; missing={report.missing_asset_ids}"
        )
    manifest = PACK.manifest
    prior_pack = REPO_ROOT / "tests/live/fixtures/higgsfield_car_v1/assets"
    for asset_id in ("car_sheet", "street_environment"):
        asset = by_id(manifest)[asset_id]
        new_path = PACK.pack_root / asset["path"]
        old_path = prior_pack / asset["local_filename"]
        assert old_path.is_file()
        assert len(old_path.read_bytes()) == asset["bytes"]
        assert new_path.read_bytes() == old_path.read_bytes()


def test_duplicate_regression_is_an_occurrence_list_not_duplicate_media() -> None:
    manifest = load_json("manifest.json")
    regression = load_json("checks/duplicate-reference-regression.json")
    physical_ids = [asset["asset_id"] for asset in manifest["assets"]]
    occurrences = regression["ordered_occurrences"]
    assert occurrences == [
        "car_sheet",
        "car_chasing_playblast",
        "passing_car_urban_ambience",
        "car_chasing_playblast",
    ]
    assert len(physical_ids) == len(set(physical_ids))
    assert set(physical_ids) == set(regression["physical_asset_ids"])
    assert regression["paid_post_count"] == 0


def test_paid_generation_was_not_run() -> None:
    assert load_json("manifest.json")["paid_generation"] == {
        "status": "not_run",
        "post_count": 0,
    }
