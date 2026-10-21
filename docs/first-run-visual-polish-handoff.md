# First-run connection visual handoff

Baseline: 58c8cff466166198a6aa80b3264685d6f6c4630d.
Authority: Product Owner's final pre-RC visual polish and isolated live acceptance prompt.

Only Connection/About presentation is authorized: compact status/helper/actions,
ComfyUI theme tokens and existing PrimeVue button/input classes, primary OAuth,
secondary collapsed manual-key entry, native HTML dialog focus/Esc, subtle About.
No new dependencies, branding, settings unrelated to auth, capability or auth changes.

Node tokens remain width 400, row 20, gap 4, section 8, Prompt 42, DOM inset 16,
inset 15. All node topology, sockets, cost badge, controls, geometry, duration,
workflow values, serializer, migration, projection and connected presentation stay
unchanged. Disconnected helper text alone becomes OpenRouter connection required.
Connection CTA remains a native non-serialized button around discovery.

Settings are application-level, status-only and common to Classic/Nodes2.
Environment: helper badge; no removal action. Session: restart helper.
Dialog: primary Sign in with OpenRouter; collapsed Use existing API key; masked
field and secondary Connect. Key is never redisplayed or persisted in frontend.
About: name, version, by ARENAS®lab; no outbound CTA or tracking.

Regression contract: full Python/frontend/Builder; exact source hash guard against
this predecessor; zero backend delta; protected frontend suffix comparison allowing
only About presentation and disconnected helper copy. Real acceptance must freeze
one commit and run separate clean source/process on 8192 as explicitly authorized.
No product source edits are permitted after that commit. Any discovered runtime or
architecture defect stops acceptance and is reported; no further commit/amend.

User explicitly authorizes isolated acceptance rather than the plugin's usual
canonical DEV-only rule. 8188, 8189 and their sources/settings are untouched.
Real OAuth may require manual Product Owner sign-in/consent. No paid inference.
