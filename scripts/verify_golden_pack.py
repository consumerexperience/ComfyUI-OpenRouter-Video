#!/usr/bin/env python3
"""Verify the test-only default Golden Pack without contacting any network/API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fixtures.golden_pack import (  # noqa: E402
    MATERIALIZATION_COMMAND,
    GoldenPackError,
    load_default_pack,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--golden-pack", default="default", choices=("default",), help="test-only pack selector"
    )
    args = parser.parse_args()
    try:
        pack = load_default_pack(selector=args.golden_pack)
        verification = pack.verify_local_assets()
    except GoldenPackError as error:
        sys.stdout.write(json.dumps({"state": "INVALID", "error": str(error)}, indent=2) + "\n")
        return 1

    result = {
        "state": verification.state,
        "pack_id": pack.pack_id,
        "selector": str(pack.selector_path.relative_to(ROOT)),
        "manifest": str(pack.manifest_path.relative_to(ROOT)),
        "canonical_order": [
            {"position": ref["position"], "type": ref["type"], "asset_id": ref["asset_id"]}
            for ref in pack.canonical_references
        ],
        "checked_asset_ids": verification.checked_asset_ids,
        "missing_asset_ids": verification.missing_asset_ids,
        "contract_checks": {
            "schema": "PASS",
            "required_media_types": "PASS",
            "semantic_roles": "PASS",
            "transport_mapping": "PASS",
            "canonical_order": "PASS",
            "duplicate_occurrence_contract": "PASS",
        },
        "paid_post_count": pack.manifest["paid_generation"]["post_count"],
        "paid_post_count_observed": 0,
    }
    if not verification.ready:
        result["materialization_command"] = MATERIALIZATION_COMMAND
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 2
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
