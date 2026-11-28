"""Read-only snapshot comparison using the production Core; no credentials or runtime writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

from openrouter_video.capabilities import capability_evolution
from openrouter_video.client import _parse_capability


def load(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    # Parsing time is not evidence of when a saved HTTP response was observed.
    models = tuple(_parse_capability(row) for row in data["data"])
    return tuple(
        replace(
            model,
            evidence_facts=tuple(
                replace(f, observed_at="UNRECORDED_SNAPSHOT_TIME")
                if f.authority.startswith("LIVE_")
                else f
                for f in model.evidence_facts
            ),
        )
        for model in models
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", type=Path, help="Optional bounded review/CI Markdown summary")
    parser.add_argument("--fail-underexposure", action="store_true")
    args = parser.parse_args()
    result = capability_evolution(load(args.previous) if args.previous else (), load(args.current))
    result["inputs"] = {
        name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for name, path in (("current", args.current), ("previous", args.previous))
        if path
    }
    result["limitations"] = [
        "Read-only catalogue/contract evidence, not paid execution proof",
        "Unknown wire mappings require upstream evidence or adapter work",
    ]
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.summary:
        summary = {
            "inputs": result["inputs"],
            "models": result["current_model_count"],
            "executable_methods": result["completeness"]["executable_method_count"],
            "dispositions": result["completeness"]["dispositions"],
            "underexposure_defect_count": result["completeness"]["underexposure_defect_count"],
            "actionable_constraints": [
                {"model_id": model["model_id"], **row}
                for model in result["completeness"]["models"]
                for row in model["rows"]
                if row.get("classification")
                in {
                    "CAPABILITY_UNDEREXPOSURE_DEFECT",
                    "STALE_EVIDENCE",
                    "MISSING_UPSTREAM_CONTRACT",
                    "IMPLEMENTATION_GAP",
                    "CONTRACT_CONFLICT",
                }
            ][:100],
            "changes": result["changes"][:100],
            "remaining_change_count": max(0, len(result["changes"]) - 100),
            "accounting_is_execution_proof": False,
        }
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(
                "\n### Read-only capability drift\n\n```json\n"
                + json.dumps(summary, indent=2)
                + "\n```\n"
            )
    sys.stdout.write(
        json.dumps(
            {
                "report": str(args.output),
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "models": result["current_model_count"],
                "methods": result["completeness"]["executable_method_count"],
            }
        )
        + "\n"
    )
    if args.fail_underexposure and result["completeness"]["underexposure_defect_count"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
