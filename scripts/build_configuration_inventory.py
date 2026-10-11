"""Render canonical UI configuration inventories without rewriting upstream evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openrouter_video.comfy.projection import canonical_options

AXES = {
    "resolution": "supported_resolutions",
    "aspect_ratio": "supported_aspect_ratios",
    "duration": "supported_durations",
    "size": "supported_sizes",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    projection = json.loads(args.input.read_text(encoding="utf-8-sig"))
    models = projection["models"]
    args.output.mkdir(parents=True, exist_ok=True)
    unions = {
        axis: list(canonical_options(axis, tuple({v for m in models for v in m[key] or []})) or ())
        for axis, key in AXES.items()
    }
    inventory = "# Canonical projected configuration inventory\n\n"
    inventory += "Display ordering only. Raw evidence order and wire values are unchanged.\n\n"
    for axis, values in unions.items():
        inventory += axis.upper() + "_GLOBAL_UNION:\n" + json.dumps(values) + "\n\n"
    inventory += (
        "AUTO / MODEL DEFAULT precedes known values; "
        "duration wire sentinel 0 is omitted/default.\n\n"
    )
    inventory += (
        "Resolution is nominal ranking, not preset-to-pixel mapping. "
        "Unknown labels are retained after known values.\n\n"
    )
    inventory += "NO_CONFIRMED_COUPLED_MODEL_IN_CURRENT_CATALOGUE\n\n"
    inventory += "## Exact Size display / wire\n\n| DISPLAY_VALUE | UPSTREAM_VALUE |\n|---|---|\n"
    for value in unions["size"]:
        inventory += f"| {value.replace('x', '×')} | {value} |\n"
    (args.output / "configuration-union.md").write_text(inventory, encoding="utf-8")
    (args.output / "configuration-union.json").write_text(
        json.dumps(unions, indent=2) + "\n", encoding="utf-8"
    )
    table = "# Canonical UI model configuration matrix\n\n"
    table += (
        "All values are canonically projected; evidence payloads retain their own "
        "upstream order. No separate Mode widget.\n\n"
    )
    headers = [
        "MODEL",
        "MODE / RELEVANT MODE SHAPE",
        "INFERENCE METHODS",
        "RESOLUTION",
        "ASPECT RATIO",
        "DURATION",
        "EXACT SIZE",
        "COUPLING",
        "EVIDENCE STATE",
    ]
    table += "| " + " | ".join(headers) + " |\n"
    table += "|---|---|---|---|---|---|---|---|---|\n"
    for model in models:
        values = [
            canonical_options(axis, tuple(model[key])) if model[key] is not None else None
            for axis, key in AXES.items()
        ]
        cells = [
            model["display_name"] + "<br>" + model["model_id"],
            "NO SEPARATE MODE; method/recipe",
            ", ".join(model["supported_inference_methods"]) or "UNKNOWN",
        ]
        cells += [", ".join(map(str, domain)) if domain else "UNKNOWN" for domain in values]
        cells += [
            "INDEPENDENT" if any(values) else "UNKNOWN",
            "LIVE_STRUCTURED_API; unknown domains remain UNKNOWN",
        ]
        table += "| " + " | ".join(cells) + " |\n"
    (args.output / "model-configuration-matrix.md").write_text(table, encoding="utf-8")


if __name__ == "__main__":
    main()
