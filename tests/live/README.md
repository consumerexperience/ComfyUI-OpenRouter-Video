# Live tests

No live test exists in Phase 3. Future live tests must remain excluded by default and require
immediate human approval, a dedicated capped DEV credential, and the applicable project gate.

## Default multimodal Golden Pack

`fixtures/default_golden_pack.json` is the test-only selector for `higgsfield_car_multimodal_v1`. Contract/mock MMR2V integration and live-smoke input resolution use this registry; the manifest under `tests/live/fixtures/` is the source of truth. The exported copy under `output/` is never read by tests or runtime.

Run zero-cost local verification:

```powershell
python scripts/verify_golden_pack.py
```

Resolve the default fixture for a separately gated live smoke:

```powershell
python scripts/resolve_live_smoke_pack.py --golden-pack default
```

The resolver only validates fixture input. It sends no network request, queues no ComfyUI workflow, and performs no paid POST. A real live Generate still requires a positively capability-validated model and immediate explicit Product Owner approval, with at most one Generate POST.

The third-party media binaries are gitignored. When missing, verification reports `MATERIALIZATION_REQUIRED`; it never downloads automatically and never falls back to production state. Materialize explicitly with:

```powershell
python scripts/materialize_higgsfield_multimodal_pack.py
```

The existing `scripts/fetch_higgsfield_car_v1.py` is used only when the older image source archive must be materialized. Synthetic fixtures remain appropriate for unit tests. For the historical image-only pack, see [Creative Golden Pack v1](fixtures/higgsfield_car_v1/README.md); that pack is not the default multimodal fixture.
