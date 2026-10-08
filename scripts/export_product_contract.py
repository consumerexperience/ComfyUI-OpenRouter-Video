#!/usr/bin/env python3
"""Export deterministic OpenRouter Video product semantics from a Git tree."""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

EXPORTER_NAME = "openrouter-video-product-contract-exporter"
EXPORTER_VERSION = "1"
GIT = shutil.which("git")
if GIT is None:
    raise RuntimeError("git executable is required")


class ExportError(RuntimeError):
    """Raised when a required product semantic cannot be recovered from source."""


class TreeReader:
    def __init__(self, repository: Path, revision: str) -> None:
        self.repository = repository
        self.revision = revision
        self.subject_sha = self._git("rev-parse", revision).strip()

    def _git(self, *args: str) -> str:
        process = subprocess.run(  # noqa: S603 - fixed executable and structured arguments
            [GIT, "-C", str(self.repository), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if process.returncode:
            raise ExportError(process.stderr.strip() or f"git {' '.join(args)} failed")
        return process.stdout

    def text(self, relative_path: str) -> str:
        return self._git("show", f"{self.subject_sha}:{relative_path}")

    def exists(self, relative_path: str) -> bool:
        process = subprocess.run(  # noqa: S603 - fixed executable and structured arguments
            [
                GIT,
                "-C",
                str(self.repository),
                "cat-file",
                "-e",
                f"{self.subject_sha}:{relative_path}",
            ],
            check=False,
            capture_output=True,
        )
        return process.returncode == 0


def _class(tree: ast.Module, name: str) -> ast.ClassDef | None:
    return next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name),
        None,
    )


def _enum_values(tree: ast.Module, name: str) -> list[str]:
    node = _class(tree, name)
    if node is None:
        return []
    values: list[str] = []
    for item in node.body:
        if (
            isinstance(item, ast.Assign)
            and len(item.targets) == 1
            and isinstance(item.targets[0], ast.Name)
            and isinstance(item.value, ast.Constant)
            and isinstance(item.value.value, str)
        ):
            values.append(item.value.value)
    return values


def _annotated_fields(tree: ast.Module, name: str) -> list[str]:
    node = _class(tree, name)
    if node is None:
        raise ExportError(f"Required class {name} is absent")
    return [
        item.target.id
        for item in node.body
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
    ]


def _call_attributes(node: ast.AST) -> list[str]:
    return [
        item.func.attr
        for item in ast.walk(node)
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute)
    ]


def _node_ids(nodes_source: str) -> list[str]:
    tree = ast.parse(nodes_source)
    values: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not node.name.startswith("OpenRouterVideo"):
            continue
        for item in ast.walk(node):
            if not isinstance(item, ast.Call):
                continue
            for keyword in item.keywords:
                if (
                    keyword.arg == "node_id"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    values.append(keyword.value.value)
    return sorted(set(values))


def _method_topology(methods: list[str]) -> dict[str, dict[str, Any]]:
    known: dict[str, dict[str, Any]] = {
        "T2V": {"required": [], "references": "none"},
        "I2V": {"required": ["first_frame"], "references": "none"},
        "FLF2V": {"required": ["first_frame", "last_frame"], "references": "none"},
        "IR2V": {"required": ["IMAGE"], "references": "exactly_one"},
        "MI2V": {"required": ["IMAGE"], "references": "at_least_two"},
        "VR2V": {"required": ["VIDEO"], "references": "at_least_one"},
        "AR2V": {"required": ["AUDIO"], "references": "at_least_one"},
        "MMR2V": {"required": ["two_distinct_media_kinds"], "references": "at_least_two"},
        "V2V_EDIT": {"required": ["source_video"], "references": "source_first"},
        "V2V_EXTEND": {"required": ["source_video"], "references": "source_first"},
    }
    unknown = sorted(set(methods) - known.keys())
    if unknown:
        raise ExportError(f"Exporter does not understand inference methods: {unknown}")
    return {method: known[method] for method in methods}


def _load_evidence(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExportError("Observed evidence must be a JSON object")
    return value


def export_contract(
    repository: Path,
    revision: str,
    checkpoint_id: str,
    contract_id: str,
    evidence_path: Path,
) -> dict[str, Any]:
    reader = TreeReader(repository.resolve(), revision)
    models_source = reader.text("src/openrouter_video/models.py")
    nodes_source = reader.text("src/openrouter_video/comfy/nodes.py")
    application_source = reader.text("src/openrouter_video/application.py")
    models = ast.parse(models_source)
    application = ast.parse(application_source)
    generate = _class(application, "GenerateService")
    resume = _class(application, "ResumeService")
    if generate is None or resume is None:
        raise ExportError("GenerateService and ResumeService are required product surfaces")
    generate_calls = _call_attributes(generate)
    resume_calls = _call_attributes(resume)
    submit_calls = generate_calls.count("submit_video")
    if submit_calls != 1:
        raise ExportError(
            f"GenerateService exposes {submit_calls} submit calls; expected exactly one"
        )
    if "submit_video" in resume_calls:
        raise ExportError("ResumeService unexpectedly has submit authority")

    reference_kinds = [value.upper() for value in _enum_values(models, "InputReferenceKind")]
    methods = _enum_values(models, "InferenceMethod")
    request_fields = _annotated_fields(models, "GenerationRequest")
    capability_fields = _annotated_fields(models, "ModelCapabilities")
    lifecycle_states = _enum_values(models, "LocalLifecycleState")
    node_ids = _node_ids(nodes_source)
    staging_present = reader.exists("src/openrouter_video/staging.py")
    native_image = reader.exists("src/openrouter_video/comfy/image.py")
    native_media = reader.exists("src/openrouter_video/comfy/native_media.py")
    persistence_source = reader.text("src/openrouter_video/persistence.py")
    observed = _load_evidence(evidence_path)

    product_owned = {
        "node_family": {
            "generate": "OpenRouterVideoGenerate",
            "resume": "OpenRouterVideoResume",
            "registered_types": node_ids,
        },
        "method_semantics": {
            "inference_method_is_local": bool(methods),
            "methods": methods,
            "topology": _method_topology(methods),
            "non_ready_behavior": "hidden_for_new_selection_preserved_when_persisted",
            "derivation_authority": "exact_model_capability_primitives_fail_closed",
        },
        "media_topology": {
            "reference_kinds": reference_kinds,
            "ordered_occurrences": "preserved",
            "duplicates": "preserved",
            "native_direct_inputs": {
                "IMAGE": native_image,
                "VIDEO": native_media,
                "AUDIO": native_media,
            },
            "source_video_first": "source_video" in request_fields,
            "incompatible_switch": "preserve_state_and_block_generate",
        },
        "controls": {
            "capability_driven": sorted(
                field
                for field in capability_fields
                if field
                in {
                    "supported_durations",
                    "supported_resolutions",
                    "supported_aspect_ratios",
                    "supported_sizes",
                    "supported_frame_types",
                    "generate_audio",
                    "seed",
                }
            ),
            "request_fields": sorted(
                field
                for field in request_fields
                if field
                in {
                    "duration",
                    "resolution",
                    "aspect_ratio",
                    "size",
                    "seed",
                    "generate_audio",
                }
            ),
            "fail_closed": True,
        },
        "persistence": {
            "workflow_compatibility": "preserve_compatible_values_and_links",
            "legacy_workflow_support": True,
            "staging_ownership_ledger": "staging_objects" in persistence_source,
            "staging_tombstone": "staging_operations" in persistence_source,
        },
        "lifecycle": {
            "states": lifecycle_states,
            "generate_submit_calls": submit_calls,
            "resume_submit_authority": False,
            "ambiguous_submit_resubmits": False,
            "poll_failure_is_generation_failure": False,
            "atomic_submit_claim": "claim_submitting" in generate_calls,
        },
        "billing_security": {
            "max_intentional_paid_submits_per_operation": 1,
            "credentials_serialized": False,
            "app_identity_runtime_override": False,
            "capabilities_fail_closed": True,
            "native_storage": {
                "enabled": staging_present,
                "private_temporary_objects": staging_present,
                "resume_can_upload": False,
                "cleanup_never_authorizes_regeneration": staging_present,
            },
        },
    }
    upstream_dynamic = {
        "catalogue_rule": (
            "project_complete_current_canonical_production_catalogue_without_fixture_substitution"
        ),
        "dynamic_fields": [
            "model_ids",
            "model_count",
            "provider_availability",
            "capability_values",
            "pricing_values",
            "catalogue_revision",
        ],
        "immutable_model_count": False,
    }
    return {
        "protocol": "openrouter-video-product-contract",
        "schema_version": 1,
        "contract_id": contract_id,
        "checkpoint_id": checkpoint_id,
        "subject_sha": reader.subject_sha,
        "exporter": {"name": EXPORTER_NAME, "version": EXPORTER_VERSION},
        "surfaces": {
            "product_owned": product_owned,
            "upstream_dynamic": upstream_dynamic,
            "observed_evidence": observed,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--revision", required=True)
    parser.add_argument("--checkpoint-id", required=True)
    parser.add_argument("--contract-id", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = export_contract(
            args.repository,
            args.revision,
            args.checkpoint_id,
            args.contract_id,
            args.evidence,
        )
    except (ExportError, OSError, json.JSONDecodeError) as exc:
        sys.stdout.write(json.dumps({"STATUS": "INVALID", "ERROR": str(exc)}) + "\n")
        return 1
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
