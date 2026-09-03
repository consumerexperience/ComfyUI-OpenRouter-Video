# Development environment

## Repository environment

- Repository: `OPENROUTER/ComfyUI-OpenRouter-Video`
- Primary interpreter: CPython 3.12.10
- Supported floor: Python 3.10
- Environment: repository-local `.venv`

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

`requirements-dev.lock` records the resolved Phase 3 environment. Production runtime does not
depend on a development environment manager.

## DEV ComfyUI

- Location: `OPENROUTER/dev/ComfyUI-DEV`
- Release: `v0.34.3`
- Commit: `87465b8f1f64a27a46f16f22b13b410494dca66d`
- Python: CPython 3.12.10 in a separate `.venv`
- Product link: NTFS junction under `custom_nodes`, targeting this repository

The DEV installation contains no production workflows, production credentials, unrelated custom
nodes, or copied product source. Run its CPU quick-test only; model execution is outside Phase 3.

## Compatibility decisions

- `UNKNOWN-PYTHON-001 — RESOLVED`: ComfyUI v0.34.3 declares Python `>=3.10`, which establishes
  the package compatibility floor.
- `UNKNOWN-COMFY-001 — RESOLVED FOR SCAFFOLD`: the inspected numbered V3 API `v0_0_2` declares
  `STABLE = False`. Phase 3 therefore pins the complete host release and commit, and uses the
  numbered API only for an empty discovery seam. It does not claim that this API is a stable
  support baseline.

A refreshed evidence gate is required before the future Comfy adapter makes any V3 support
promise. This gate does not block Phase 4 Headless Core.
