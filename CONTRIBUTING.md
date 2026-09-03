# Contributing

## Development setup

Use Python 3.12 for the primary development environment. The supported package floor is Python
3.10. Create `.venv`, install `.[dev]`, and run the commands documented in
[docs/development.md](docs/development.md).

The dedicated ComfyUI installation belongs at the workspace-level `dev/ComfyUI-DEV` path. Never
develop against a production ComfyUI installation and never copy the repository into
`custom_nodes`; use the documented junction/editable-install arrangement.

## Required checks

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests
python -m build
python -m pip_audit
```

All default checks cost zero and must not contact OpenRouter.

## Architecture invariants

- Core imports no ComfyUI code.
- The Comfy adapter stays thin and receives no independent product semantics.
- Raw HTTP remains behind the future Client / RequestPolicy / Transport boundary.
- Generate may attempt at most one paid POST; Resume has no submit capability.
- Credentials and attribution never become workflow configuration.
- Provider-specific shortcuts require architecture review.

## Change classification

Classify a change before implementation: scaffold/tooling, approved implementation, bug fix,
external-contract change, Specification change, Architecture/ADR change, security/billing
change, or release. The latter five require the applicable project gate before editing.

## Provenance and pull requests

Study ComfyUI behavior and public interfaces, then implement independently. Do not copy
substantial GPL-3.0 source into this MIT project. Pull requests must describe scope, evidence,
tests, security/billing impact, and any remaining gate. Paid tests and publishing are never part
of ordinary PR CI.
