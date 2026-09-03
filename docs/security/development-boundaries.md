# Development security boundaries

```text
COMFY PROD
  outside agent scope; real workflows and credentials

COMFY DEV
  clean pinned host; synthetic state; repository junction

PRODUCT REPOSITORY
  source, tests, governance; no credentials

MOCK OPENROUTER
  localhost only; synthetic fixtures

LIVE OPENROUTER
  future human-approved capped-key session only
```

Phase 3 does not access environment credentials, make OpenRouter requests, inspect production
ComfyUI, publish packages, or freeze official application identity.
