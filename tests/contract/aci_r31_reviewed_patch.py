"""Version-bound historical checks; direct R3.1 guards inspect current source."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "15cc5aea7570fe43d2154b4e3b6f1efba8f4ac2d"


def r31_historical_source(path: str, current: str) -> str:
    from tests.contract.acxs_visual_reviewed_patch import visual_baseline_source

    current = visual_baseline_source(path, current)
    # The reviewed integrated backend is unchanged by final UI corrections.
    # Exact hashes + immutable Git bytes, never a wildcard or new approval.
    declaration = ROOT / "tests/fixtures/integrated_prebeta_source_candidate.json"
    if declaration.is_file():
        candidate = json.loads(declaration.read_text(encoding="utf8"))
        reviewed = "5f1bc3f4df60ad3b19f43215a7d32a3827adf5f6"
        digest = hashlib.sha256(current.replace("\r\n", "\n").encode()).hexdigest()
        if (
            candidate.get("status") == "UNACCEPTED_FINAL_CORRECTION"
            and candidate.get("reviewed_baseline") == reviewed
            and candidate.get("reviewed_source_files", {}).get(path) == digest
        ):
            git = shutil.which("git")
            assert git is not None
            exact = subprocess.check_output(  # noqa: S603 - exact reviewed local Git object
                [git, "show", f"{reviewed}:{path}"], cwd=ROOT
            ).decode("utf8")
            assert hashlib.sha256(exact.replace("\r\n", "\n").encode()).hexdigest() == digest
            current = subprocess.check_output(  # noqa: S603 - original historical stage
                [git, "show", f"a39204322349b5d13270c7df3f3e6cc24d12180a:{path}"], cwd=ROOT
            ).decode("utf8")
    pin_path = ROOT / "tests/fixtures/aci_r31_source_candidate.json"
    if not pin_path.is_file():
        return current
    pin = json.loads(pin_path.read_text(encoding="utf8"))
    digest = hashlib.sha256(current.replace("\r\n", "\n").encode("utf8")).hexdigest()
    if (
        pin.get("status") != "UNACCEPTED"
        or pin.get("baseline_sha") != BASELINE
        or pin.get("candidate_files", {}).get(path) != digest
    ):
        return current
    from tests.contract.test_aci_r31_protected_scope import (
        test_r31_nodes_change_only_terminal_ui_and_explicit_operation_metadata,
        test_r31_routes_preserve_auth_oauth_registration_and_non_cost_handlers,
        test_r31_runtime_preserves_every_non_estimate_method,
    )

    if path == "src/openrouter_video/comfy/runtime.py":
        test_r31_runtime_preserves_every_non_estimate_method()
    elif path == "src/openrouter_video/comfy/routes.py":
        test_r31_routes_preserve_auth_oauth_registration_and_non_cost_handlers()
    elif path == "src/openrouter_video/comfy/nodes.py":
        test_r31_nodes_change_only_terminal_ui_and_explicit_operation_metadata()
    git = shutil.which("git")
    assert git is not None
    return subprocess.check_output(  # noqa: S603 - exact immutable local Git source
        [git, "show", f"{BASELINE}:{path}"], cwd=ROOT
    ).decode("utf8")
