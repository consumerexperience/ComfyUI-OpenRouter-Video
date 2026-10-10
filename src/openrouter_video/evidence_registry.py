"""Reviewed data enrichment, with explicit provenance and conflict retention."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from openrouter_video.models import (
    CapabilityEvidenceSource,
    CapabilityFact,
    CapabilityFactState,
    InferenceMethod,
    InputReferenceCapabilities,
    InputReferenceCapabilityField,
    InputReferenceKind,
    ModelCapabilities,
    ModelCapabilityField,
)

MANIFEST_PATH = Path(__file__).with_name("data") / "capability-evidence.json"
KNOWN_FACTS = frozenset(
    {
        "supports_text_only",
        "source_required",
        "reference_kinds",
        "max_reference_count",
        "mixed_reference_kinds",
        "supports_edit",
        "supports_extend",
        "preferred_inference_method",
    }
)


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """No remote updates. Validate artifact integrity before consuming any fact."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("models"), list):
        raise ValueError("Evidence manifest schema invalid")
    expected = data.get("content_hash")
    content = {key: value for key, value in data.items() if key != "content_hash"}
    actual = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if expected != actual:
        raise ValueError("Evidence manifest integrity invalid")
    ids = [entry["exact_model_id"] for entry in data["models"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Evidence manifest ambiguous model identity")
    for entry in data["models"]:
        if not isinstance(entry["exact_model_id"], str) or not entry["exact_model_id"].strip():
            raise ValueError("Evidence manifest model identity invalid")
        if not isinstance(entry.get("facts"), dict):
            raise ValueError("Evidence manifest facts invalid")
        for key, evidence in entry["facts"].items():
            if not isinstance(evidence, dict):
                raise ValueError("Evidence manifest fact invalid")
            for required in ("authority", "source_reference", "observed_at", "scope"):
                if not isinstance(evidence.get(required), str) or not evidence[required].strip():
                    raise ValueError("Evidence manifest provenance invalid")
            source = urlsplit(evidence["source_reference"])
            if source.scheme != "https" or source.hostname != "openrouter.ai":
                raise ValueError("Evidence manifest source must be first-party HTTPS")
            if (
                datetime.fromisoformat(evidence["observed_at"].replace("Z", "+00:00")).tzinfo
                is None
            ):
                raise ValueError("Evidence manifest freshness must include timezone")
            value = evidence.get("value")
            if value is None:
                continue
            if key in {
                "supports_text_only",
                "source_required",
                "mixed_reference_kinds",
                "supports_edit",
                "supports_extend",
            } and not isinstance(value, bool):
                raise ValueError("Evidence manifest boolean invalid")
            if key == "max_reference_count" and (type(value) is not int or value < 0):
                raise ValueError("Evidence manifest reference limit invalid")
            if key == "reference_kinds":
                if not isinstance(value, list) or not value:
                    raise ValueError("Evidence manifest reference kinds invalid")
                for kind in value:
                    InputReferenceKind(kind)
            if key == "preferred_inference_method":
                InferenceMethod(value)
    return data  # type: ignore[no-any-return]


def enrich_capabilities(
    model: ModelCapabilities, manifest: dict[str, Any] | None = None
) -> ModelCapabilities:
    data = load_manifest() if manifest is None else manifest
    entry = next(
        (entry for entry in data["models"] if entry["exact_model_id"] == model.model_id), None
    )
    if entry is None:
        return model
    facts = list(model.evidence_facts)
    changes: dict[str, Any] = {}
    refs = model.input_reference_capabilities or InputReferenceCapabilities()
    ref_changes: dict[str, Any] = {}
    ref_conflicts = set(refs.conflicts)
    model_conflicts = set(model.capability_conflicts)
    unmapped = set(model.unmapped_capability_keys)
    reference_fields = {
        "reference_kinds": InputReferenceCapabilityField.REFERENCE_KINDS,
        "max_reference_count": InputReferenceCapabilityField.MAX_REFERENCE_COUNT,
        "mixed_reference_kinds": InputReferenceCapabilityField.MIXED_REFERENCE_KINDS,
    }
    for key, evidence in entry["facts"].items():
        value = evidence["value"]
        conflicts = tuple(evidence.get("conflicting_evidence", ()))
        state = (
            CapabilityFactState.CONFLICT
            if conflicts
            else (
                CapabilityFactState.UNKNOWN
                if value is None
                else CapabilityFactState.UNSUPPORTED
                if value is False
                else CapabilityFactState.SUPPORTED
            )
        )
        current = getattr(refs, key, None) if key in reference_fields else getattr(model, key, None)
        if key in reference_fields and current is not None:
            source_key = {
                "reference_kinds": "reference_kinds_source",
                "max_reference_count": "max_reference_count_source",
                "mixed_reference_kinds": "mixed_reference_kinds_source",
            }[key]
            if getattr(refs, source_key) is None:
                ref_changes[source_key] = CapabilityEvidenceSource.LEVEL_A
        effective = (
            frozenset(InputReferenceKind(item) for item in value)
            if key == "reference_kinds" and value is not None
            else value
        )
        if current is not None and current != effective and effective is not None:
            state = CapabilityFactState.CONFLICT
            conflicts += (current, value)
            if key in reference_fields:
                ref_conflicts.add(reference_fields[key])
            if key == "supports_edit":
                model_conflicts.add(ModelCapabilityField.EDIT)
            if key == "supports_extend":
                model_conflicts.add(ModelCapabilityField.EXTEND)
        fact = CapabilityFact(
            model.model_id,
            key,
            value,
            state,
            evidence["authority"],
            evidence["source_reference"],
            evidence["observed_at"],
            evidence["scope"],
            data["artifact_version"],
            conflicts,
        )
        if fact not in facts:
            facts.append(fact)
        if key not in KNOWN_FACTS:
            unmapped.add(key)
        elif (
            current is None
            and effective is not None
            and not conflicts
            and key != "preferred_inference_method"
        ):
            if key in reference_fields:
                ref_changes[key] = effective
                source_key = {
                    "reference_kinds": "reference_kinds_source",
                    "max_reference_count": "max_reference_count_source",
                    "mixed_reference_kinds": "mixed_reference_kinds_source",
                }[key]
                ref_changes[source_key] = CapabilityEvidenceSource.EVIDENCE_OVERLAY
            else:
                changes[key] = effective
                if key in ("supports_edit", "supports_extend"):
                    changes[
                        "edit_support_source" if key == "supports_edit" else "extend_support_source"
                    ] = CapabilityEvidenceSource.EVIDENCE_OVERLAY
    refs = replace(refs, **ref_changes, conflicts=frozenset(ref_conflicts))
    return replace(
        model,
        **changes,
        input_reference_capabilities=refs,
        evidence_facts=tuple(facts),
        unmapped_capability_keys=tuple(sorted(unmapped)),
        capability_conflicts=frozenset(model_conflicts),
    )


def preferred_method(model_id: str) -> InferenceMethod | None:
    data = load_manifest()
    entry = next((entry for entry in data["models"] if entry["exact_model_id"] == model_id), None)
    value = entry["facts"].get("preferred_inference_method", {}).get("value") if entry else None
    return InferenceMethod(value) if value is not None else None
