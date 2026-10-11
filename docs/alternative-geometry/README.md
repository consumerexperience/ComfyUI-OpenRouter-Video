# Alternative geometry representations

Owner-authorized patch against c86accb. SIZE_SEMANTICS = ALTERNATIVE_GEOMETRY_REPRESENTATION.

Normalized geometry serializes resolution/aspect_ratio only. Exact geometry serializes only an explicit size. On load, legacy explicit size is authoritative exact intent; inactive normalized values are cleared, without preset/pixel mapping. Clearing Exact Size restores normalized defaults from confirmed domains, not from pixel dimensions. For both domains, a fresh workflow defaults to normalized; the existing nonserialized Advanced button exposes the alternative as Exact Size. Size-only models expose Exact Size directly. Unknown evidence remains unknown. Invalid legacy size remains visible and preserved, and is rejected by existing validation.

Raw ambiguous requests are rejected by both unchanged RequestValidator and the added serializer guard before network submission. Existing Generate/Resume, billing, media, duration, layout, pricing, capability evidence, and credentials are protected. No new mode field, provider branch or dependency.

Evidence: https://openrouter.ai/docs/guides/overview/multimodal/video-generation (read 2026-10-11), Request Parameters describes size as exact WIDTHxHEIGHT, interchangeable with resolution + aspect_ratio. Mutual exclusion is the explicit owner-approved conservative product policy; no claim about upstream simultaneous-field precedence or preset-to-pixel mapping is introduced. This supersedes the old size-unknown product classification only, not the unknown model mapping evidence.
