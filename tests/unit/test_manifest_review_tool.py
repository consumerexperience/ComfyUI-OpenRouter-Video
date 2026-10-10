from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from openrouter_video.evidence_registry import MANIFEST_PATH


def test_promotion_requires_exact_review_hash_and_keeps_byte_exact_rollback(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    rollback = tmp_path / "rollback.json"
    report = tmp_path / "report.json"
    original = MANIFEST_PATH.read_bytes()
    baseline.write_bytes(original)
    data = json.loads(original)
    data["artifact_version"] = "synthetic-next-version"
    content = {k: v for k, v in data.items() if k != "content_hash"}
    data["content_hash"] = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    candidate.write_text(json.dumps(data), encoding="utf-8")
    command = [
        sys.executable,
        str(Path(__file__).parents[2] / "scripts/review_capability_manifest.py"),
        str(candidate),
        str(baseline),
        "--report",
        str(report),
        "--promote-reviewed",
        "--rollback-file",
        str(rollback),
        "--expected-hash",
    ]
    rejected = subprocess.run(command + ["wrong-hash"], capture_output=True, check=False)  # noqa: S603
    assert rejected.returncode != 0
    assert baseline.read_bytes() == original
    assert not rollback.exists()
    accepted = subprocess.run(command + [data["content_hash"]], capture_output=True, check=False)  # noqa: S603
    assert accepted.returncode == 0, accepted.stderr
    assert baseline.read_bytes() == candidate.read_bytes()
    assert rollback.read_bytes() == original
    protected_report = subprocess.run(  # noqa: S603 - fixed local script, synthetic paths
        command[: command.index("--report")] + ["--report", str(baseline)],
        capture_output=True,
        check=False,
    )
    assert protected_report.returncode != 0
    assert baseline.read_bytes() == candidate.read_bytes()
