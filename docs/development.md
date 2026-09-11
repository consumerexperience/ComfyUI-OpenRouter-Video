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
nodes, or copied product source. Phase 6 uses its CPU quick-test and the test-only compatibility
probe; model inference and live OpenRouter traffic remain out of scope.

## Compatibility decisions

- `UNKNOWN-PYTHON-001 — RESOLVED`: ComfyUI v0.34.3 declares Python `>=3.10`, which establishes
  the package compatibility floor.
- `UNKNOWN-COMFY-001 — RESOLVED FOR PHASE 6`: the adapter supports only the exact host release,
  commit, and numbered `comfy_api.v0_0_2` surface above. A missing version/capability marker fails
  closed. Production never imports `comfy_api.latest` or executor internals.
- Pinned `PromptExecutor` testing proved cross-Queue output reuse despite `not_idempotent=True`.
  Both public nodes therefore use a JSON-safe, process-local monotonic `fingerprint_inputs` token.
  The token is only a Comfy cache workaround and never becomes business identity.

| Host | Status |
| --- | --- |
| ComfyUI `v0.34.3` / `87465b8f...` / `comfy_api.v0_0_2` | `SUPPORTED` |
| Any other release or commit | `UNSUPPORTED` |
| Missing or mismatched numbered API capability | `FAIL CLOSED` |

## Phase 5 headless core

Headless Core development and tests do not require ComfyUI. The production source resolves only the
named `OPENROUTER_API_KEY` environment variable, while default tests inject a synthetic provider
and never inspect a production credential. Network tests use HTTPX MockTransport or the existing
loopback fault harness; they do not contact OpenRouter.

SQLite tests use temporary databases. They exercise WAL, synchronous FULL, schema versioning,
operation/job uniqueness, exact Decimal-as-TEXT cost storage, corruption handling, restart, and
same-operation concurrency. Media tests write only generated temporary `.part`, MP4, and WebM
fixtures below pytest temporary roots.

## Phase 6 adapter gate

Run the repository suite from this repository's `.venv`. Run host compatibility from the pinned
Comfy DEV interpreter:

```powershell
cd ..\dev\ComfyUI-DEV
.\.venv\Scripts\python.exe main.py --quick-test-for-ci --cpu
$env:PYTHONPATH="..\..\ComfyUI-OpenRouter-Video\src;$PWD"
.\.venv\Scripts\python.exe ..\..\ComfyUI-OpenRouter-Video\tests\comfy_dev_probe.py --cpu
```

`PromptExecutor` appears only in `tests/comfy_dev_probe.py`; it is not a production dependency.
