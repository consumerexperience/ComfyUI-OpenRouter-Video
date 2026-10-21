# OAuth callback result-page visibility

Owner-authorized visual delta from `806b6b90dc1ca1413ae44c303e9017229f64340c`.

The original response was complete HTTP 200, UTF-8 HTML with a matching
187-byte Content-Length. It rendered in a normal browser tab. Its foreground
was black and its background transparent. The actual popup root cause remains
inconclusive; this change implements the owner's explicit theme-independent
visibility requirement rather than claiming a proven popup diagnosis.

Only result-page presentation changes: complete Russian HTML, opaque background
and contrasting foreground on both html and body, centered responsive layout,
and UTF-8 bytes. aiohttp calculates Content-Length from those bytes. A precise
SHA-256 CSP style hash permits the static local CSS; scripts and external
resources remain prohibited. There is no auto-close or transaction data.

The receiver class and its state, PKCE, timeout, single-transaction and cleanup
behavior are unchanged. Credential exchange, validation, persistence, frontend
state, nodes and generation are unchanged.

Raw-socket tests verify status, headers, body byte length, strict UTF-8, Russian
messages, sanitized failures, full delivery and listener closure. Contrast tests
verify opaque theme-independent colors satisfy WCAG AAA normal-text contrast.
The existing duplicate, expiry and exchange regressions remain in place.

Real owner OAuth-popup acceptance is separate from synthetic test evidence.
If the exact committed candidate still shows a blank popup, stop without further
source changes and inspect that popup's DOM/navigation/response.
