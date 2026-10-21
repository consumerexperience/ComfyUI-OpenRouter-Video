# OAuth callback transport surgical repair

Starting SHA: 5b7c524b6dac1440d31d26a95309f785b4428adb.
Owner authorized only callback transport. Root cause: ComfyUI rejects cross-site
OAuth navigation before the plugin route. ComfyUI source/origin protection/CORS
are untouched. No proxy or global security exemption is used.

A short-lived aiohttp receiver binds an owned IPv4 socket to 127.0.0.1:0.
The generated redirect is http://127.0.0.1:<OS-port>/callback with random state in
its query. Carrying state inside callback_url preserves it when the provider adds
code; it does not rely on an undocumented top-level state echo. PKCE S256 and the
existing one-time key exchange remain unchanged. No code/query/verifier logging.

The receiver accepts only one GET transaction, rejects missing/wrong/duplicate
state, missing code, provider rejection, repeat callback and expiry. Access logging
is disabled. Static success/failure pages have no assets/scripts/diagnostics;
no-store, no-referrer and restrictive CSP are set. Timeout, failure, completion
and replacement all close the listener and discard the verifier. No temporary
OAuth data enters storage. Only validated final access credentials reach the
existing keyring/session abstraction. Environment remains authoritative.

Auth start constructs its own redirect; frontend no longer supplies a ComfyUI
callback. The old ComfyUI callback route is removed. Existing polling updates
connection UI without refresh/restart. A source-equality regression protects the
entire polished frontend except that request-body transport change. Core credential,
keyring, Generate/Resume, capabilities, serialization and AppIdentity stay unchanged.

Default tests use only synthetic loopback transactions and mocked PKCE exchange.
One repair commit is required before exact-candidate isolated live acceptance.
No paid inference or remote actions are authorized.
