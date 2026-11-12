"""Synthetic future contracts exercise adaptation, not provider runtime claims."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

from openrouter_video.capabilities import (
    CapabilityObservation,
    CapabilityService,
    RequestValidator,
    capability_changes,
    capability_completeness,
    capability_completeness_report,
    capability_evolution,
    catalogue_metadata,
    eligible_methods,
    request_witness,
    semantic_fingerprint,
)
from openrouter_video.client import _parse_capability, bounded_catalogue_metadata
from openrouter_video.configuration import project_method
from openrouter_video.errors import TransportError
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.models import InferenceMethod, ModelCapabilities, ProviderOption
from openrouter_video.persistence import JobStore


def future(mid: str = "synthetic/new-model") -> dict[str, Any]:
    return {
        "id": mid,
        "supports_text_only": True,
        "supported_durations": [5, 15],
        "supported_resolutions": ["720p", "4K"],
        "supported_aspect_ratios": ["16:9"],
        "reference_kinds": ["image", "video"],
        "max_reference_count": 4,
        "mixed_reference_kinds": True,
        "seed": False,
        "generate_audio": False,
    }


def test_new_id_and_exact_kling4_use_the_same_generic_reference_contract() -> None:
    for mid in ("synthetic/new-model", "kwaivgi/kling-v4.0"):
        model = enrich_capabilities(_parse_capability(future(mid)))
        assert InferenceMethod.MMR2V in eligible_methods(model)
        assert project_method(model, "T2V")["controls"]["resolution"]["values"] == ["720p", "4K"]
        for method in eligible_methods(model):
            witness = request_witness(model, method)
            assert witness is not None
            RequestValidator().validate_capabilities(witness, model)


def test_mixed_requires_explicit_positive_contract_not_native_modalities() -> None:
    raw = future()
    raw.pop("mixed_reference_kinds")
    assert InferenceMethod.MMR2V not in eligible_methods(_parse_capability(raw))
    raw["mixed_reference_kinds"] = False
    assert InferenceMethod.MMR2V not in eligible_methods(_parse_capability(raw))


def test_new_enum_and_typed_provider_option_reach_validator_and_wire() -> None:
    raw = future()
    model = _parse_capability(raw)
    profile = project_method(model, "T2V")
    # A future API supplies the complete existing structured schema, including route.
    profile = {k: v for k, v in profile.items() if k in {"state", "controls", "topology"}}
    profile["controls"]["provider_options"] = {
        "state": "SUPPORTED",
        "required": False,
        "providers": {"synthetic": {"quality": {"type": "string", "values": ["ultra", "draft"]}}},
    }
    raw["allowed_passthrough_parameters"] = ["quality", "unknown_option"]
    # Derived admission/completeness diagnostics are not upstream recipe fields.
    for key in ("execution_domain", "limit_completeness", "reconciliation"):
        profile["topology"].pop(key, None)
    raw["request_shape_profiles"] = {"schema_version": 1, "methods": {"T2V": profile}}
    model = _parse_capability(raw)
    witness = request_witness(model, InferenceMethod.T2V)
    assert witness is not None
    request = replace(witness, provider_options=(ProviderOption("synthetic", "quality", "ultra"),))
    RequestValidator().validate_capabilities(request, model)
    wire = cast(dict[str, Any], request.to_openrouter_payload())
    assert wire["provider"]["options"]["synthetic"]["quality"] == "ultra"
    rows = {r["path"]: r for r in capability_completeness(model)["rows"]}
    assert rows["provider_options.quality"]["disposition"] == "SUPPORTED_EXECUTABLE"
    assert rows["provider_options.unknown_option"]["disposition"] == "EVIDENCE_GAP"


def test_unknown_operation_retained_but_not_promoted() -> None:
    raw = future()
    raw["request_shape_profiles"] = {
        "schema_version": 1,
        "methods": {"NEW_OPERATION": {"state": "SUPPORTED", "novel_wire": "unknown"}},
    }
    model = _parse_capability(raw)
    rows = {r["path"]: r for r in capability_completeness(model)["rows"]}
    assert rows["methods.NEW_OPERATION"]["disposition"] == "IMPLEMENTATION_GAP"
    assert "NEW_OPERATION" in catalogue_metadata(model)["request_shape_profiles"]["methods"]
    malformed: tuple[Any, ...] = ([], None, {"unrecognized_control": {"state": "SUPPORTED"}})
    for controls in malformed:
        raw["request_shape_profiles"]["methods"] = {
            "T2V": {"state": "SUPPORTED", "controls": controls}
        }
        rejected = _parse_capability(raw)
        assert project_method(rejected, "T2V")["state"] == "UNKNOWN"
        assert (
            next(
                r
                for r in capability_completeness(rejected)["rows"]
                if r["path"] == "request_shape_profiles"
            )["disposition"]
            == "EVIDENCE_GAP"
        )


def test_incomplete_operation_flags_and_malformed_explicit_recipes_fail_closed() -> None:
    raw = future()
    raw.update(supports_edit=True, supports_extend=True)
    model = _parse_capability(raw)
    assert InferenceMethod.V2V_EDIT not in eligible_methods(model)
    assert InferenceMethod.V2V_EXTEND not in eligible_methods(model)
    raw["request_shape_profiles"] = {
        "schema_version": 1,
        "methods": {"MMR2V": {"state": "SUPPORTED", "controls": {}}},
    }
    assert project_method(_parse_capability(raw), "MMR2V")["state"] == "UNKNOWN"


def test_complete_new_operation_recipe_has_explicit_wire_discriminator() -> None:
    raw = future()
    raw["allowed_passthrough_parameters"] = ["task"]
    raw["request_shape_profiles"] = {
        "schema_version": 1,
        "methods": {
            "V2V_EDIT": {
                "state": "SUPPORTED",
                "controls": {
                    "prompt": {"state": "SUPPORTED"},
                    "provider_options": {
                        "state": "SUPPORTED",
                        "required": True,
                        "providers": {
                            "synthetic": {
                                "task": {"type": "string", "values": ["edit"], "default": "edit"}
                            }
                        },
                    },
                },
                "topology": {
                    "fixed": ["source_video"],
                    "reference_kinds": [],
                    "kind_sets": [[]],
                    "min": 0,
                    "max": 0,
                    "per_kind_max": {},
                },
            }
        },
    }
    model = _parse_capability(raw)
    witness = request_witness(model, InferenceMethod.V2V_EDIT)
    assert witness is not None
    wire = cast(dict[str, Any], witness.to_openrouter_payload())
    assert wire["provider"]["options"]["synthetic"]["task"] == "edit"
    assert InferenceMethod.MMR2V not in eligible_methods(
        model
    )  # Explicit recipe set is authoritative.
    raw["request_shape_profiles"]["schema_version"] = 999
    assert project_method(_parse_capability(raw), "MMR2V")["state"] == "UNKNOWN"
    report = capability_completeness(_parse_capability(raw))
    assert (
        next(r for r in report["rows"] if r["path"] == "request_shape_profiles")["disposition"]
        == "EVIDENCE_GAP"
    )


def test_json_object_order_does_not_change_completeness_fingerprint() -> None:
    raw = future()
    a = capability_completeness_report((_parse_capability(raw),))
    b = capability_completeness_report((_parse_capability(dict(reversed(list(raw.items())))),))
    assert semantic_fingerprint(a) == semantic_fingerprint(b)


def test_evolution_reports_control_activation_domain_change_and_distinct_accounting_units() -> None:
    before = future()
    after = dict(before, seed=True, supported_resolutions=["720p", "4K", "8K"])
    report = capability_evolution((_parse_capability(before),), (_parse_capability(after),))
    changes = {(r["method"], r["control"]): r["change"] for r in report["control_changes"]}
    assert changes["T2V", "seed"] == "ACTIVATED"
    assert changes["T2V", "resolution"] == "VALUE_CHANGED"
    completeness = report["completeness"]
    assert sum(completeness["dispositions"].values()) == completeness["discovered_field_count"]
    assert completeness["projection_dispositions"]


def test_persistence_job_and_billing_methods_are_unchanged_from_baseline() -> None:
    import ast
    import shutil
    import subprocess

    root = Path(__file__).resolve().parents[2]
    git = shutil.which("git")
    assert git is not None
    before = subprocess.check_output(  # noqa: S603 - fixed local immutable source
        [
            git,
            "show",
            "721d9ebac1ee1c7cb83cd15ab9faff0262f3924e:src/openrouter_video/persistence.py",
        ],
        cwd=root,
        text=True,
        encoding="utf-8",
    )
    after = (root / "src/openrouter_video/persistence.py").read_text(encoding="utf-8")

    def methods(text: str) -> dict[str, str]:
        cls = next(
            n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == "JobStore"
        )
        return {
            n.name: ast.dump(n, include_attributes=False)
            for n in cls.body
            if isinstance(n, ast.FunctionDef)
            and n.name
            not in {"_initialize", "replace_capability_catalog", "load_capability_evolution"}
        }

    assert methods(before) == methods(after)


def test_metadata_type_presence_bounds_redaction_and_sqlite_roundtrip(tmp_path: Path) -> None:
    raw = future()
    raw.update(
        new_false=False,
        new_zero=0,
        new_null=None,
        new_empty=[],
        new_nested={"typed": [True, 3, "x"]},
        secret="must-not-persist",  # noqa: S106 - synthetic redaction fixture
    )
    model = _parse_capability(raw)
    retained = catalogue_metadata(model)
    for key in ("new_false", "new_zero", "new_null", "new_empty", "new_nested"):
        assert retained[key] == raw[key] and type(retained[key]) is type(raw[key])
    assert "absent" not in retained
    assert retained["secret"] == {"discovery_omitted": "SENSITIVE_FIELD"}
    assert (
        bounded_catalogue_metadata({"large": "x" * 2049})["large"]["discovery_omitted"]
        == "TEXT_BOUND"
    )
    store = JobStore(tmp_path / "catalogue.sqlite")
    now = datetime.now(timezone.utc)
    drift = capability_changes((), (model,))
    store.replace_capability_catalog((model,), now, evolution=drift)
    cached = store.load_capability_catalog()
    assert cached is not None
    assert catalogue_metadata(cached[1][0]) == retained
    assert store.load_capability_evolution() == drift


def test_semantic_drift_distinguishes_type_removal_and_ignores_clock_and_domain_order() -> None:
    raw = future()
    raw["unknown"] = 0
    a = _parse_capability(raw)
    changed = dict(raw, unknown=False, supported_durations=[15, 5])
    b = _parse_capability(changed)
    changes = capability_changes((a,), (b,))["changes"]
    assert changes == [{"model_id": a.model_id, "field": "unknown", "change": "TYPE_CHANGED"}]
    assert semantic_fingerprint(
        {"supported_durations": [5, 15], "observed_at": "a"}
    ) == semantic_fingerprint({"supported_durations": [15, 5], "observed_at": "b"})
    assert capability_changes((a,), ())["changes"][0]["change"] == "REMOVED"
    assert semantic_fingerprint({"unknown": []}) != semantic_fingerprint({"unknown": None})


def test_backend_concurrent_refresh_single_flight_and_fallback_not_removal(tmp_path: Path) -> None:
    class Discovery:
        calls = 0

        async def list_video_models(self) -> tuple[ModelCapabilities, ...]:
            self.calls += 1
            await asyncio.sleep(0.01)
            return (_parse_capability(future()),)

    client = Discovery()
    store = JobStore(tmp_path / "catalogue.sqlite")
    now = datetime.now(timezone.utc)
    service = CapabilityService(client=client, store=store, now=lambda: now)

    async def run() -> list[CapabilityObservation]:
        return await asyncio.gather(*(service.catalog() for _ in range(5)))

    observations = asyncio.run(run())
    assert client.calls == 1
    assert all(o.source_state == "FRESH" for o in observations)
    drift = store.load_capability_evolution()
    cached = store.load_capability_catalog()
    assert drift is not None and drift["current_model_count"] == 1
    assert cached is not None and cached[0] > now - timedelta(minutes=15)


def test_failed_refresh_retains_last_observation_and_never_reports_removal(tmp_path: Path) -> None:
    class Failing:
        async def list_video_models(self) -> tuple[ModelCapabilities, ...]:
            raise TransportError("offline")

    async def no_sleep(_: float) -> None:
        pass

    now = datetime.now(timezone.utc)
    store = JobStore(tmp_path / "catalogue.sqlite")
    model = _parse_capability(future())
    drift = capability_changes((), (model,))
    store.replace_capability_catalog((model,), now - timedelta(minutes=20), evolution=drift)
    service = CapabilityService(client=Failing(), store=store, now=lambda: now, sleep=no_sleep)
    observation = asyncio.run(service.catalog())
    assert observation.source_state == "STALE_FALLBACK"
    assert observation.models == (model,)
    assert observation.evolution == drift
