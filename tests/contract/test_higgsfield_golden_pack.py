"""Zero-cost integrity checks for the local Higgsfield Golden Pack contract."""

from __future__ import annotations

import hashlib
import json
import struct
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK = REPO_ROOT / "tests/live/fixtures/higgsfield_car_v1"


def load_json(relative_path: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((PACK / relative_path).read_text(encoding="utf-8")))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_golden_contract_is_single_five_second_shot() -> None:
    contract = load_json("checks/contract.json")
    assert contract["id"] == "higgsfield_car_front_wheel_v1"
    assert contract["duration_seconds"] == 5
    assert contract["generation"]["shot_count"] == 1
    assert contract["generation"]["continuous_take"] is True
    assert contract["generation"]["cuts"] == 0
    assert contract["generation"]["audio"] is False
    assert contract["reference_policy"]["ordered_refs"] == [
        "car_sheet.png",
        "loc_street_main.png",
    ]
    assert contract["reference_policy"]["preserve_duplicate_occurrences"] is True
    assert contract["machine_assertions"]["generate_paid_post_count_max"] == 1
    assert contract["machine_assertions"]["resume_paid_post_count"] == 0


def test_multimodal_transport_is_a_separate_level_two_contract() -> None:
    level1 = load_json("checks/contract.json")
    level2 = load_json("checks/contract-level2-mmr2v.json")
    assert level1["generation"]["audio"] is False
    assert level2["duration_seconds"] == 5
    assert level2["required_media_types"] == ["image", "video", "audio"]
    assert "approval" in " ".join(level2["preconditions"]).lower()


def test_prompt_is_short_and_explicitly_one_take() -> None:
    prompt = (PACK / "prompts/openrouter_smoke.md").read_text(encoding="utf-8")
    assert "continuous 5-second" in prompt
    assert "Camera remains mechanically locked" in prompt
    assert "No cut" in prompt
    assert "Shot 2" not in prompt
    assert len(prompt.split()) < 150


def test_provenance_and_manifest_are_consistent() -> None:
    manifest = load_json("manifest.json")
    provenance = load_json("provenance.json")
    assert manifest["source"]["archive_sha256"] == provenance["source_archive"]["sha256"]
    assert manifest["source"]["archive_bytes"] == provenance["source_archive"]["bytes"]
    assert [item["local_filename"] for item in manifest["assets"]] == [
        item["local_filename"] for item in provenance["assets"]
    ]
    for item in manifest["assets"]:
        origin = next(
            source
            for source in provenance["assets"]
            if source["local_filename"] == item["local_filename"]
        )
        assert item["sha256"] == origin["sha256"]
        assert item["bytes"] == origin["bytes"]
        assert item["modified"] is False


def test_materialized_archive_and_assets_match_manifest() -> None:
    manifest = load_json("manifest.json")
    archive = PACK / manifest["source"]["archive_local_path"]
    required = [archive, *(PACK / asset["path"] for asset in manifest["assets"])]
    if not all(path.is_file() for path in required):
        pytest.skip(
            "Official third-party media is not materialized; run the fetch command in README.md"
        )

    assert archive.stat().st_size == manifest["source"]["archive_bytes"]
    assert sha256(archive) == manifest["source"]["archive_sha256"]
    with zipfile.ZipFile(archive) as source_zip:
        assert source_zip.testzip() is None
        for asset in manifest["assets"]:
            path = PACK / asset["path"]
            content = path.read_bytes()
            assert len(content) == asset["bytes"]
            assert hashlib.sha256(content).hexdigest() == asset["sha256"]
            assert source_zip.read(asset["upstream_archive_member"]) == content
            assert content[:8] == b"\x89PNG\r\n\x1a\n"
            width, height = struct.unpack(">II", content[16:24])
            assert [width, height] == asset["dimensions"]
            color_type = content[25]
            channels = {2: 3, 6: 4}.get(color_type)
            assert channels == asset["channels"]
