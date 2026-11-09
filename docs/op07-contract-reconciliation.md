# OP-07 exact-model contract reconciliation — uninstalled patch candidate

Baseline 058f5bcdd462a2a71f4f85151d9bbba3bc09bcf9. Owner authorization:
6497404b-6167-4414-99db-c1d02410a623. Checked 2026-11-08. No paid execution.

## Google: limited restoration, not full-domain certification

The new reviewed data profiles expose **T2V, I2V, FLF2V only at
8 seconds / 720p / 16:9** for `google/gemini-omni-1.2-flash` and
`google/veo-3.1-lite`. This deliberately small common configuration does not
turn the catalogue's independent lists into a Cartesian product. The UI shows
prompt, method, duration, resolution and aspect controls and required frame
sockets. Exact Size, seed, audio toggle, references, edit/extend and `task` /
`previous_job_id` are NOT certified by this patch and remain unexposed.

Evidence chain (three separate authorities, none sufficient alone):

1. Public `GET https://openrouter.ai/api/v1/videos/models`: exact IDs, bounded
   control domains, first_frame and last_frame for both; 8, 720p, 16:9 are present.
   Gemini canonical slug is gemini-omni-1.2-flash-20261105. Stored public receipt
   in the previous analysis dossier is reused, not an authenticated response.
2. Exact-model first-party documentation:
   - https://openrouter.ai/google/gemini-omni-1.2-flash
   - https://docs.cloud.google.cn/gemini-enterprise-agent-platform/models/gemini/omni-1-2-flash?hl=en
     Model version gemini-omni-1.2-flash, release November 5. Generation 3–15s;
     two-frame interpolation 3–10s, 720p and landscape supported. 8s lies within
     both bounds. Additional modes have extra semantics not implemented here.
   - https://openrouter.ai/google/veo-3.1-lite
   - https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate
     The **3.1 Lite Generate** section confirms text, image, first/last generation,
     4/6/8s, 720p/1080p, 16:9/9:16. Only 8s/720p/16:9 is enabled here; other
     resolution/duration relations remain uncertified. OpenRouter's dated slug
     and Google's version naming differ: this is a common documented capability
     intersection, not a claim of binary-identical native deployment.
3. https://openrouter.ai/docs/guides/overview/multimodal/video-generation
   The served Video API defines required model and prompt; optional duration,
   resolution, aspect_ratio and typed frame_images. Fixed roles map to existing
   frame_type/image_url serialization. No new request field or provider branch.

Request witnesses run through the actual RequestValidator and existing serializer
and are submitted **only to HttpxTransport.for_test(MockTransport)**. This proves
local shape/encoding consistency, not generation success or billing, native image
limits enforcement, or complete provider certification. Native documentation is
used as a bounded applicability cross-check, not transplanted as an entire profile.

## Findings kept OPEN

- Veo wider domains and combinations: `VEO_DURATION_RESOLUTION_SHAPES` remains
  OPEN outside the narrow restored intersection. No old audit record is edited.
- Kling Pro: `KLING_PROVIDER_SIZE_CONFLICT` remains OPEN. No inferred downscale
  or substitution of 1080P for catalogue 720p. O1/Standard likewise lack a reviewed
  complete exact served request profile; public model descriptions and historic
  READY do not resolve those profiles. All three remain backend-known, ineligible.
- Gemini 1.1 and mischief: independent exact-model shape reconciliation remains
  OPEN; do not copy the 1.2 profile to nearby names or versions.
- FLUX edit/upscale and Avatar: specialized operation/source requirements remain
  unimplemented; no new operations are introduced to make the list look complete.

Automatic activation is conditional on confirmed profiles becoming available in
the existing registry/effective capabilities. Current public metadata contains no
documented complete `request_shape_profiles` field; arbitrary JSON claiming
SUPPORTED is not accepted as proof. No invented upstream field parser, whitelist,
automatic evidence authoring or remote code/data updater is introduced. An entirely
new contract requiring new adapter code still needs implementation and review.

The frozen artifact and existing TEST/DEV/RC/PROD installations are unchanged.
This candidate requires Owner UI review and qualification before release.
