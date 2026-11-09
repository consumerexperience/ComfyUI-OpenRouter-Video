"""Bind the Owner-selected frozen baseline and an explicitly UNACCEPTED delta.

Does not modify accepted snapshots. Candidate pins let historical shields inspect
their original checkpoint; focused OP07 tests verify the newly authorized behavior.
"""

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "058f5bcdd462a2a71f4f85151d9bbba3bc09bcf9"
GIT = shutil.which("git")
ALLOWED = {
    "src/openrouter_video/capabilities.py": "capabilities",
    "src/openrouter_video/eligibility.py": "capabilities",
    "src/openrouter_video/comfy/projection.py": "capabilities",
    "src/openrouter_video/comfy/routes.py": "capabilities",
    "src/openrouter_video/data/capability-evidence.json": "evidence_registry",
    "web/openrouter_video.js": "workflow_persistence",
}


def git(*args):
    return subprocess.check_output(  # noqa: S603 - fixed Git, local constant revision and paths
        [GIT, "-C", str(ROOT), *args], text=True, encoding="utf-8"
    )


def digest(text):
    return hashlib.sha256(text.replace("\r\n", "\n").encode()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    template = json.loads(
        (ROOT / "contracts/product/accepted/native-media-e2e-v1.product-contract.json").read_text()
    )
    baseline = copy.deepcopy(template)
    baseline.update(
        contract_id="op07-frozen-baseline", checkpoint_id="op05-frozen-058f5bc", subject_sha=BASE
    )
    owners = {
        key: surface
        for surface, files in template["surfaces"]["product_owned"].items()
        for key in files
    }
    baseline["surfaces"]["product_owned"] = {}
    for name in git("ls-tree", "-r", "--name-only", BASE, "src", "web").splitlines():
        if Path(name).suffix not in {".py", ".json", ".js"}:
            continue
        key = name.replace("/", "~1").replace(".", "_")
        surface = owners.get(key, "capabilities")
        baseline["surfaces"]["product_owned"].setdefault(surface, {})[key] = digest(
            git("show", BASE + ":" + name)
        )
    changes = []
    for name, surface in ALLOWED.items():
        key = name.replace("/", "~1").replace(".", "_").replace("~", "~0")
        changes.append(
            {
                "path": f"/surfaces/product_owned/{surface}/{key}",
                "operations": ["add", "replace"],
                "reason": (
                    "Owner 6497404b: bounded discovery/eligibility/refresh delta; "
                    "Owner architectural correction 8fad0a0c: reuse existing Core "
                    "capability service; not release acceptance."
                ),
            }
        )
    delta = dict(
        protocol="openrouter-video-contract-delta",
        schema_version=1,
        delta_id="op07-discovery-remediation",
        baseline_checkpoint=baseline["checkpoint_id"],
        baseline_sha=BASE,
        risk_tier="B",
        intended_delta=[
            "Supported-only selection, live refresh and lossless legacy intent; "
            "bounded documented Google profiles."
        ],
        allowed_semantic_changes=changes,
        protected_surfaces=[
            "/surfaces/product_owned/security",
            "/surfaces/product_owned/submit_resume",
            "/surfaces/product_owned/AppIdentity",
            "/surfaces/product_owned/storage",
        ],
        expected_components=list(ALLOWED),
        required_gates=[
            "baseline_declaration",
            "semantic_diff",
            "negative_space_tests",
            "python",
            "frontend",
            "serializer",
        ],
        unexpected_scope_policy="STOP_AND_REPORT",
    )
    save(ROOT / "contracts/product/baselines/op07-frozen-058f5bc.json", baseline)
    save(ROOT / "contracts/product/deltas/op07-discovery-remediation.contract-delta.json", delta)
    current = copy.deepcopy(baseline)
    current["surfaces"]["product_owned"] = {}
    for path in list((ROOT / "src/openrouter_video").rglob("*")) + list(
        (ROOT / "web").glob("*.js")
    ):
        if not path.is_file() or path.suffix not in {".py", ".json", ".js"}:
            continue
        name = path.relative_to(ROOT).as_posix()
        key = name.replace("/", "~1").replace(".", "_")
        current["surfaces"]["product_owned"].setdefault(owners.get(key, "capabilities"), {})[
            key
        ] = digest(path.read_text(encoding="utf-8"))
    save(ROOT / "contracts/product/candidates/op07-discovery-source.json", current)
    pin = dict(
        state="UNACCEPTED_IMPLEMENTATION_CANDIDATE",
        baseline_sha=BASE,
        candidate_files={
            name: digest((ROOT / name).read_text(encoding="utf-8")) for name in ALLOWED
        },
    )
    save(ROOT / "tests/fixtures/op07_discovery_candidate.json", pin)
    guard_path = ROOT / "tests/tooling/product_contract_guard.py.fixture"
    spec = importlib.util.spec_from_file_location(
        "op07_guard", guard_path, loader=SourceFileLoader("op07_guard", str(guard_path))
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result = module.semantic_diff(baseline, current, delta)
    save(ROOT / "contracts/product/candidates/op07-discovery-guard.json", result)
    sys.stdout.write(json.dumps(result) + "\n")
    return 0 if result["STATUS"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
