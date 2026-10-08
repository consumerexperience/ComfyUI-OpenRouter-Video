# Higgsfield Creative Golden Pack v1

This pack defines **GOLDEN SMOKE 01 — FRONT WHEEL RIG**: one five-second automotive video-generation smoke using the official Higgsfield car-commercial visual world. It is a compact regression input, not a multi-shot demo.

## Source and materialization

The official source is Higgsfield's [Cinematic Car Commercial — Full Breakdown](https://higgsfield.ai/blog/ai-car-commercial-youtube-guide). The page publishes `all_assets_here_car_commercial.zip` and the exact three-shot driving B-roll prompt. The first shot is explicitly one continuous 0–5 s rig-mounted front-wheel take; the other two shots and their cuts are excluded from Level 1.

Run from the product repository to fetch, verify, and materialize the original corpus and the selected assets:

```powershell
python scripts/fetch_higgsfield_car_v1.py
```

The script downloads the official CDN object by HTTP byte ranges, checks the complete archive SHA-256 and ZIP CRCs, extracts the archive without rewriting member bytes, and writes the two canonical asset copies only when absent. Existing files with different bytes cause a hard failure. The local binary directories are gitignored because the source page does not establish redistribution rights for the third-party media. This keeps the local corpus available without implying permission to republish it with the OSS repository.

`manifest.json` records selectors and technical properties. `provenance.json` binds each canonical asset to its exact upstream filename, official page, archive identity, and SHA-256. The canonical subset is intentionally only:

1. `car_sheet.png` — vehicle identity and body/wheel reference (`@car_sheet`).
2. `loc_street_main.png` — the matching residential Los Angeles road environment (`@loc_street_main`).

The selected files are byte-for-byte copies of ZIP members. Tunnel, highway, dealership, character, and prop files are not pulled into this shot. The archive does not contain the reference tags `@loc_tunnel`, `@hero_03`, or `@loc_street` as files; this pack does not invent substitutes for them.

## Prompts

- [`prompts/upstream.md`](prompts/upstream.md) preserves the upstream technical block and Shot 1 wording verbatim, with the published URL and section context.
- [`prompts/openrouter_smoke.md`](prompts/openrouter_smoke.md) is the short, stable OpenRouter-specific regression prompt. Use the two references in manifest order when the selected live model accepts two image references; otherwise use `car_sheet.png` alone. Never silently reorder or deduplicate references.

## Test pyramid

| Level | Cost | Contract |
| --- | --- | --- |
| 0 — Local / zero cost | Zero | Schema, serialization, reference ordering and duplicate preservation, Resume with zero paid POSTs, persistence, transport, archive/asset hash verification. |
| 1 — Golden paid smoke | Paid; immediate owner approval required | Exactly 5 s, one continuous automotive shot, minimal image references. Cheap live validation with a visually rewarding result. |
| 2 — Multimodal paid smoke | Paid; separate approval required | Exactly 5 s, IMAGE + VIDEO + AUDIO, only when validating MMR2V/multimodal transport. See [`checks/contract-level2-mmr2v.json`](checks/contract-level2-mmr2v.json); it is separate from Level 1. |
| 3 — Cinematic acceptance | Paid; milestone/release approval required | 15 s maximum by default. |
| 30 s+ | Paid; demo/showcase only | Manual cinematic evaluation. Never regression testing. |

Level 0 uses `python -m pytest tests/contract/test_higgsfield_golden_pack.py`. It never contacts OpenRouter. Materialized third-party binaries are optional for public CI; when present, the test checks their exact hashes and PNG headers. Run the full repository zero-cost test suite separately as needed.

## Assertions and acceptance

[`checks/contract.json`](checks/contract.json) separates machine-checkable request and output assertions from [`checks/visual-acceptance.md`](checks/visual-acceptance.md), which requires human review. No vision evaluator or automated visual PASS is claimed.

For the paid smoke, the existing project billing invariant remains controlling: one Generate may submit at most one paid POST; Resume has no submit capability; ambiguity never permits a retry. The fixture itself does not submit anything. A live paid submit remains gated on immediate explicit owner approval and a live model/capability choice. Do not run the download script with an OpenRouter key, and do not use this fixture to probe unresolved VIDEO data-URL behavior.

## Rights and immutable asset policy

The local source archive and extracted corpus are third-party tutorial downloads, preserved unchanged for local testing. Public redistribution rights were not established by the source page; binaries are therefore not checked into Git. Tracked files contain only prompts, selectors, hashes, metadata, checks, and fetch instructions.

An asset is identified by exact bytes plus SHA-256, source URL, upstream filename, and role. Do not edit, resize, transcode, recompress, or replace a binary under this version. Any byte change requires a new asset identity or pack version and an updated manifest.
