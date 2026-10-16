# Pre-RC first-run connection evidence

Evidence date: 2026-10-16. This record separates external facts from the product decision.

## Confirmed first-party facts

- OpenRouter documents a real PKCE flow at <https://openrouter.ai/docs/guides/overview/auth/oauth>.
  The flow supports localhost callbacks on arbitrary ports, S256 code challenges, and a
  code exchange at `POST https://openrouter.ai/api/v1/auth/keys` that returns a user-controlled
  API key. This is suitable for a local ComfyUI connection flow; no OAuth is simulated.
- OpenRouter's video model catalogue remains a read-only authenticated GET at
  `https://openrouter.ai/api/v1/videos/models`. The connection flow uses this request for
  validation and never calls `POST /videos`.
- ComfyUI frontend officially supports extension settings through `app.registerExtension({
  settings: [...] })`; settings values are persisted through the backend `/settings` API,
  according to <https://github.com/Comfy-Org/ComfyUI_frontend/blob/main/docs/SETTINGS.md>.
  Therefore the plugin registers a custom settings renderer that persists no credential value.

## Unknown or unavailable evidence

- No first-party, cross-platform ComfyUI extension API for secure secret storage was identified
  in the reviewed current settings and extension contracts. The existing plugin dependency set
  also contains no dedicated keyring library.

## Controlled product decision

- Use documented OpenRouter PKCE when the user chooses Sign in. Keep the exchanged key only in
  a process-local backend store for the current ComfyUI session. Offer masked manual API-key
  entry in the Settings renderer as a fallback. Resolve `OPENROUTER_API_KEY` first, then the
  interactive session value. Disconnect clears only the interactive value.
- Settings, node widgets, workflow serialization, queue/history, frontend storage, logs and
  receipts receive status labels only. Catalogue validation is the only network action after
  connection; no paid inference is part of first-run UX.
