"""Bind historical shields to exact, unaccepted ACI source plus current scope tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACI_BASELINE = "f8ba174347bd4bfed155dc64aec1d7168c39c1fa"


def aci_historical_source(path: str, current: str) -> str:
    """Only a pinned candidate can substitute its unchanged historical baseline."""
    pin = json.loads(
        (ROOT / "tests/fixtures/aci_v1_source_candidate.json").read_text(encoding="utf8")
    )
    digest = hashlib.sha256(current.replace("\r\n", "\n").encode("utf8")).hexdigest()
    if (
        pin.get("status") != "UNACCEPTED"
        or pin.get("baseline_sha") != ACI_BASELINE
        or pin.get("candidate_files", {}).get(path) != digest
    ):
        return current
    if path == "src/openrouter_video/comfy/runtime.py":
        # Do not bypass current paid/storage/lifecycle protection merely because
        # the candidate's exact hash is declared. Run its current AST guard too.
        from tests.contract.test_aci_v1_protected_scope import (
            test_aci_runtime_changes_only_existing_estimate_branch,
        )

        test_aci_runtime_changes_only_existing_estimate_branch()
    git = shutil.which("git")
    assert git is not None
    return subprocess.check_output(  # noqa: S603 - fixed local Git and pinned source path
        [git, "show", f"{ACI_BASELINE}:{path}"], cwd=ROOT
    ).decode("utf8")
