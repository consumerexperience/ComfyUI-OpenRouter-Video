from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from openrouter_video.capabilities import RequestValidator
from openrouter_video.client import _parse_capability
from openrouter_video.configuration import (
    CONFIGURATION_KEY,
    configuration_status,
    finite_domain,
    profile_constraints,
    project_configuration,
)
from openrouter_video.errors import ProductFailureError
from openrouter_video.evidence_registry import enrich_capabilities, load_manifest
from openrouter_video.models import CapabilityFactState, GenerationRequest, ModelCapabilities
from openrouter_video.persistence import JobStore


def relation(*, complete: bool = True, when: dict[str, object] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "relations": [
            {
                "axes": ["resolution", "aspect_ratio", "duration"],
                "when": when or {},
                "complete": complete,
                "allowed": [
                    {"resolution": "720p", "aspect_ratio": "16:9", "duration": [4, 8]},
                    {"resolution": "720p", "aspect_ratio": "9:16", "duration": 4},
                    {"resolution": "1080p", "aspect_ratio": "16:9", "duration": 4},
                ],
            }
        ],
    }


def model(rules: dict[str, Any] | None = None) -> ModelCapabilities:
    return _parse_capability(
        {
            "id": "synthetic/future-model",
            "supports_text_only": True,
            "supported_resolutions": ["720p", "1080p"],
            "supported_aspect_ratios": ["16:9", "9:16"],
            "supported_durations": [4, 8],
            **({CONFIGURATION_KEY: rules} if rules else {}),
        }
    )


def test_independent_domains_do_not_require_individual_tuple_evidence() -> None:
    independent = model()
    request = GenerationRequest(
        independent.model_id, "test", resolution="1080p", aspect_ratio="9:16", duration=8
    )
    RequestValidator().validate_capabilities(request, independent)
    projected = project_configuration(independent, {}, {"inference_method": "T2V"})
    assert projected["status"] == "READY"
    assert projected["options"] == {
        "resolution": ["720p", "1080p"],
        "aspect_ratio": ["16:9", "9:16"],
        "duration": [4, 8],
        "size": None,
    }


def test_explicit_relation_cannot_create_a_false_cartesian_tuple() -> None:
    coupled = model(relation())
    with pytest.raises(ProductFailureError, match="CONFIRMED_INCOMPATIBLE"):
        RequestValidator().validate_capabilities(
            GenerationRequest(
                coupled.model_id, "test", resolution="1080p", aspect_ratio="9:16", duration=4
            ),
            coupled,
        )
    projected = project_configuration(coupled, {"resolution": "1080p"}, {})
    assert projected["options"]["aspect_ratio"] == ["16:9"]  # type: ignore[index]
    assert projected["options"]["duration"] == [4]  # type: ignore[index]


def test_aspect_ratio_reprojects_duration_and_each_control_can_repair_itself() -> None:
    coupled = model(relation())
    projected = project_configuration(
        coupled, {"resolution": "720p", "aspect_ratio": "9:16", "duration": 8}, {}
    )
    assert projected["status"] == "CONFIRMED_INCOMPATIBLE"
    assert projected["options"]["duration"] == [4]  # type: ignore[index]
    assert projected["options"]["aspect_ratio"] == ["16:9"]  # type: ignore[index]


@pytest.mark.parametrize(
    "scope", [{"inference_method": "I2V"}, {"mode": "example-mode"}, {"generate_audio": True}]
)
def test_context_dependent_projection(scope: dict[str, object]) -> None:
    coupled = model(relation(when=scope))
    projected = project_configuration(coupled, {"resolution": "1080p"}, scope)
    assert projected["options"]["aspect_ratio"] == ["16:9"]  # type: ignore[index]
    unmatched = {key: False if value is True else "different" for key, value in scope.items()}
    assert project_configuration(coupled, {"resolution": "1080p"}, unmatched)["options"][
        "aspect_ratio"
    ] == ["16:9", "9:16"]  # type: ignore[index]


def test_partial_known_relation_fails_closed_only_for_unknown_coupled_tuple() -> None:
    coupled = model(relation(complete=False))
    known = {"resolution": "720p", "aspect_ratio": "16:9", "duration": 8}
    unknown = {"resolution": "1080p", "aspect_ratio": "9:16", "duration": 8}
    assert configuration_status(profile_constraints(coupled), known, {}) == "READY"
    assert configuration_status(profile_constraints(coupled), unknown, {}) == "UNKNOWN_COMBINATION"
    with pytest.raises(ProductFailureError, match="UNKNOWN_COMBINATION"):
        RequestValidator().validate_capabilities(
            GenerationRequest(
                coupled.model_id, "test", resolution="1080p", aspect_ratio="9:16", duration=8
            ),
            coupled,
        )


def test_exact_sizes_are_kept_separate_and_do_not_invent_preset_dimensions() -> None:
    exact = _parse_capability({"id": "synthetic/exact", "supported_sizes": ["752x560", "1112x834"]})
    options = project_configuration(exact, {}, {})["options"]
    assert options["size"] == ["752x560", "1112x834"]  # type: ignore[index]
    assert options["resolution"] is None  # type: ignore[index]
    assert options["aspect_ratio"] is None  # type: ignore[index]


def test_future_structured_model_and_finite_range_need_no_model_code() -> None:
    future = _parse_capability(
        {
            "id": "future/new-id-not-in-product-code",
            "supported_durations": {"min": 4, "max": 12, "step": 2},
            CONFIGURATION_KEY: relation(),
        }
    )
    assert future.supported_durations == (4, 6, 8, 10, 12)
    assert profile_constraints(future)
    assert CONFIGURATION_KEY not in future.unmapped_capability_keys
    assert project_configuration(future, {"resolution": "1080p"}, {})["options"][
        "aspect_ratio"
    ] == ["16:9"]  # type: ignore[index]


@pytest.mark.parametrize(
    "raw",
    [
        {"min": 1, "max": 100000, "step": 1},
        {"min": 4, "max": 9, "step": 2},
        {"min": 4, "max": 8, "step": 0},
        {"min": True, "max": 8, "step": 1},
    ],
)
def test_malformed_or_unbounded_ranges_do_not_fabricate_options(raw: object) -> None:
    with pytest.raises(ValueError):
        finite_domain(raw, numeric=True)


def test_unknown_configuration_vocabulary_is_unmapped_and_submit_blocked() -> None:
    rules = relation()
    rules["relations"][0]["novel_motion_control"] = True
    future = model(rules)
    assert CONFIGURATION_KEY in future.unmapped_capability_keys
    with pytest.raises(ProductFailureError, match="UNMAPPED_UPSTREAM_CAPABILITY"):
        RequestValidator().validate_capabilities(GenerationRequest(future.model_id, "test"), future)


def test_constraints_roundtrip_existing_cache_without_a_database_migration(tmp_path: Path) -> None:
    original = model(relation())
    now = datetime.now(timezone.utc)
    store = JobStore(tmp_path / "cache.sqlite3")
    store.replace_capability_catalog((original,), now)
    restored = store.load_capability_catalog()
    assert restored is not None
    assert profile_constraints(restored[1][0]) == profile_constraints(original)
    assert project_configuration(
        restored[1][0], {"resolution": "1080p"}, {}
    ) == project_configuration(original, {"resolution": "1080p"}, {})


def test_reviewed_manifest_constraints_are_a_data_only_update_and_conflicts_survive(
    tmp_path: Path,
) -> None:
    manifest = load_manifest()
    manifest["models"].append(
        {
            "exact_model_id": "synthetic/future-model",
            "facts": {
                CONFIGURATION_KEY: {
                    "value": relation(),
                    "authority": "EXACT_OFFICIAL_MODEL_PAGE",
                    "source_reference": "https://openrouter.ai/synthetic/future-model",
                    "observed_at": "2026-10-11T00:00:00Z",
                    "scope": "synthetic test-only reviewed relation",
                },
            },
        }
    )
    import hashlib

    content = {k: v for k, v in manifest.items() if k != "content_hash"}
    manifest["content_hash"] = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    reviewed = load_manifest(path)
    enriched = enrich_capabilities(model(), reviewed)
    assert profile_constraints(enriched)
    contradictory = enrich_capabilities(model(relation(complete=False)), reviewed)
    assert any(f.state is CapabilityFactState.CONFLICT for f in contradictory.evidence_facts)
    assert (
        project_configuration(
            contradictory, {"resolution": "720p", "aspect_ratio": "16:9", "duration": 4}, {}
        )["status"]
        == "UNKNOWN_COMBINATION"
    )


def test_current_catalogue_configuration_values_are_exhaustively_represented() -> None:
    root = Path(__file__).resolve().parents[2]
    audit = json.loads(
        (root / "docs/adaptive-generation-controls/evidence/live-catalogue.json").read_text()
    )
    for raw in audit["payload"]["data"]:
        normalized = _parse_capability(raw)
        options = project_configuration(normalized, {}, {})["options"]
        for axis, key in {
            "resolution": "supported_resolutions",
            "aspect_ratio": "supported_aspect_ratios",
            "duration": "supported_durations",
            "size": "supported_sizes",
        }.items():
            assert options[axis] == raw.get(key), (raw["id"], axis)  # type: ignore[index]
        assert project_configuration(normalized, {}, {})["status"] == "READY"


def test_known_coupling_without_a_context_never_becomes_independence() -> None:
    coupled = model(relation(when={"reference_count": [1, 2]}))
    assert configuration_status(profile_constraints(coupled), {}, {}) == "UNKNOWN_COMBINATION"
    assert configuration_status(profile_constraints(coupled), {}, {"reference_count": 0}) == "READY"
