"""Presentation hierarchy preserves truth, wire values and untouched evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from openrouter_video.client import _parse_capability
from openrouter_video.comfy.projection import canonical_options, project_model

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads(
    (ROOT / "tests/fixtures/configuration_option_order.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES)
def test_canonical_order_preserves_every_value(case: dict[str, Any]) -> None:
    original = tuple(case["input"])
    result = canonical_options(case["axis"], original)
    assert result == tuple(case["expected"])
    assert original == tuple(case["input"])
    assert len(result or ()) == len(original)


def test_null_and_future_unparseable_domains_stay_available() -> None:
    assert canonical_options("size", None) is None
    values = ("9" * 400 + "x1", "unknown", "640x480")
    assert set(canonical_options("size", values) or ()) == set(values)


def test_all_30_models_change_only_ui_order() -> None:
    raw = json.loads(
        (ROOT / "docs/adaptive-generation-controls/evidence/live-catalogue.json").read_text(
            encoding="utf-8"
        )
    )
    axes = {
        "resolution": "supported_resolutions",
        "aspect_ratio": "supported_aspect_ratios",
        "duration": "supported_durations",
        "size": "supported_sizes",
    }
    for record in raw["payload"]["data"]:
        capability = _parse_capability(record)
        before = capability.evidence_facts
        projected = project_model(capability, datetime.now(timezone.utc))
        for axis, name in axes.items():
            original = getattr(capability, name)
            actual = getattr(projected, name)
            assert actual == canonical_options(axis, original)
            assert actual is None if original is None else sorted(actual) == sorted(original)
            assert original == (tuple(record[name]) if record.get(name) is not None else None)
        assert capability.evidence_facts == before
