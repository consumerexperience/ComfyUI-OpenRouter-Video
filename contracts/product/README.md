# OpenRouter Video Product Contract

This directory contains product-owned instances of the generic Product Contract Guard protocol from
OpenRouter Video Builder `0.5.0-rc.2+codex.20261008`.

- `accepted/` contains reconstructed or canonically accepted semantic baselines.
- `current/` contains deterministic candidate exports.
- `deltas/` contains Product Owner-authorized semantic change envelopes.
- `evidence/` contains provenance-labelled observations; it never defines production semantics.
- `acceptance-index.json` distinguishes historical bootstrap from future canonical acceptance.

Generic schemas, validation and semantic diff logic remain in the Builder package. Run
`scripts/export_product_contract.py` against an exact Git revision, then validate and diff with the
side-by-side Builder RC. Never update an accepted snapshot merely to make a regression green.
