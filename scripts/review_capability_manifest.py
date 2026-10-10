"""Offline validated data review, semantic diff, promotion and exact rollback.

Promotion changes only the explicitly supplied file and preserves its previous
bytes. Normal execution never invokes this tool or fetches remote evidence.
"""

import argparse
import json
import shutil
from pathlib import Path

from openrouter_video.evidence_registry import load_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--promote-reviewed", action="store_true")
    parser.add_argument("--expected-hash")
    parser.add_argument("--rollback-file", type=Path)
    args = parser.parse_args()
    protected_paths = {args.candidate.resolve(), args.baseline.resolve()}
    if args.rollback_file is not None:
        protected_paths.add(args.rollback_file.resolve())
    if args.report.resolve() in protected_paths:
        parser.error("Report must not overwrite candidate, baseline or rollback")
    candidate = load_manifest(args.candidate)
    baseline = load_manifest(args.baseline)
    old = {e["exact_model_id"]: e["facts"] for e in baseline["models"]}
    new = {e["exact_model_id"]: e["facts"] for e in candidate["models"]}
    changes = [
        {"exact_model_id": model, "before": old.get(model), "after": new.get(model)}
        for model in sorted(old.keys() | new.keys())
        if old.get(model) != new.get(model)
    ]
    args.report.write_text(
        json.dumps(
            {
                "baseline_hash": baseline["content_hash"],
                "candidate_hash": candidate["content_hash"],
                "changes": changes,
                "review_required": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if args.promote_reviewed:
        if args.expected_hash != candidate["content_hash"] or args.rollback_file is None:
            parser.error("Promotion requires the reviewed exact hash and a rollback file")
        if args.rollback_file.exists():
            parser.error("Rollback file already exists; refusing to overwrite")
        if args.candidate.resolve() == args.baseline.resolve():
            parser.error("Candidate must be distinct from baseline")
        shutil.copyfile(args.baseline, args.rollback_file)
        temporary = args.baseline.with_suffix(args.baseline.suffix + ".candidate")
        if temporary.exists():
            parser.error("Temporary promotion file already exists")
        shutil.copyfile(args.candidate, temporary)
        load_manifest(temporary)
        temporary.replace(args.baseline)


if __name__ == "__main__":
    main()
