"""Geometry relations and local wire intent; no model-specific behavior or tier heuristic."""

from __future__ import annotations

import itertools
import json
import re
from collections.abc import Sequence
from importlib.resources import files


def geometry_profile(
    resolutions: Sequence[str] | None,
    aspects: Sequence[str] | None,
    sizes: Sequence[str] | None,
    relations: Sequence[dict[str, object]] = (),
    reviewed: Sequence[dict[str, object]] = (),
) -> dict[str, object]:
    """Partial ratio facts never imply a resolution tier or a full confirmed tuple."""
    tuples: list[dict[str, object]] = []
    for size in sizes or ():
        match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", size)
        if not match:
            continue
        width, height = map(int, match.groups())
        candidates = []
        for aspect in aspects or ():
            ratio = re.fullmatch(r"([1-9][0-9]*):([1-9][0-9]*)", aspect)
            if ratio:
                numerator, denominator = map(int, ratio.groups())
                # At most one physical pixel rounded on one dimension. Integer arithmetic only.
                if abs(width * denominator - height * numerator) <= max(numerator, denominator):
                    candidates.append(aspect)
        tuples.append(
            {
                "resolution": None,
                "aspect_ratio": candidates[0] if len(candidates) == 1 else None,
                "size": size,
                "provenance": "EXACT_DIMENSIONS_RATIONAL_ONE_PIXEL_TOLERANCE",
                "confidence": "SAFE_DERIVED" if len(candidates) == 1 else "UNKNOWN",
            }
        )
    for relation in relations:
        axes = relation.get("axes", [])
        if not isinstance(axes, list) or not {"resolution", "aspect_ratio", "size"} <= set(axes):
            continue
        # Scoped rules cannot be promoted into unconditional geometry facts.
        if relation.get("when") or relation.get("complete") is not True:
            continue
        allowed = relation.get("allowed", [])
        if not isinstance(allowed, list):
            continue
        for row in allowed:
            if not isinstance(row, dict):
                continue
            values: list[list[str]] = []
            for axis in ("resolution", "aspect_ratio", "size"):
                value = row.get(axis)
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    break
                values.append(value)
            if len(values) != 3:
                continue
            for resolution, aspect, size in itertools.product(*values):
                if (
                    resolution in (resolutions or ())
                    and aspect in (aspects or ())
                    and size in (sizes or ())
                ):
                    tuples.append(
                        {
                            "resolution": resolution,
                            "aspect_ratio": aspect,
                            "size": size,
                            "provenance": "EXPLICIT_STRUCTURED_CONFIGURATION_RELATION",
                            "confidence": "CONFIRMED",
                        }
                    )
    for entry in reviewed:
        if (
            entry.get("confidence") == "CONFIRMED"
            and entry.get("provenance")
            and entry.get("source_reference")
            and entry.get("resolution") in (resolutions or ())
            and entry.get("aspect_ratio") in (aspects or ())
            and entry.get("size") in (sizes or ())
        ):
            tuples.append(dict(entry))
    return {"version": 1, "tuples": tuples}


def reviewed_geometry(model_id: str) -> list[dict[str, object]]:
    """Additional exact-document relations are versioned reviewed data, never code branches."""
    data = json.loads(
        files("openrouter_video").joinpath("data/geometry-relations.json").read_text()
    )
    entries = data.get("profiles", {}).get(model_id, [])
    return [entry for entry in entries if isinstance(entry, dict)]


def wire_geometry(
    authority: str, resolution: str | None, aspect: str | None, size: str | None
) -> tuple[str | None, str | None, str | None]:
    """Authority is a local Comfy workflow field, never an OpenRouter field."""
    if authority == "NORMALIZED":
        return resolution, aspect, None
    if authority == "EXACT":
        if size is None:
            raise ValueError("Exact geometry requires an explicit size.")
        return None, None, size
    if authority or (size is not None and (resolution is not None or aspect is not None)):
        raise ValueError("Ambiguous saved geometry: explicitly edit a geometry control.")
    return resolution, aspect, size
