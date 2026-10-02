# Native Media Bridge

Connect Load Video, Load Audio or Load Image directly to the ordered reference sockets of OpenRouter Video Generate. Choose VR2V for video references, AR2V for audio references, MMR2V for mixed types, or Source Video for edit/extend. Model capabilities still decide which methods, types and counts are available. URL reference helper nodes remain compatible; connected occurrences and duplicates survive workflow reload.

IMAGE uses the existing direct PNG bridge. VIDEO becomes MP4/H.264; AUDIO becomes WAV PCM16 with its original rate and mono/stereo channels. Batches larger than one, empty media, non-finite audio and unsupported shapes fail locally. Objects are limited to 256 MiB and total encoded VIDEO/AUDIO to 512 MiB. Files are converted after capability validation, streamed to private storage, and removed locally on every normal/error/cancellation exit.

## One-time local storage setup

Install this plugin's dependencies with `python -m pip install .` from this checkout using the ComfyUI environment's interpreter. Configure these variables locally before starting ComfyUI, alongside the user's existing OpenRouter key. Never put storage settings or credentials in workflow widgets or JSON.

| Variable | R2 reference value |
| --- | --- |
| OPENROUTER_VIDEO_S3_ENDPOINT | https://ACCOUNT_ID.r2.cloudflarestorage.com |
| OPENROUTER_VIDEO_S3_REGION | auto |
| OPENROUTER_VIDEO_S3_BUCKET | user's private bucket name |
| OPENROUTER_VIDEO_S3_ACCESS_KEY_ID | local storage access key |
| OPENROUTER_VIDEO_S3_SECRET_ACCESS_KEY | local storage secret key |
| OPENROUTER_VIDEO_S3_SESSION_TOKEN | optional, for compatible backends using session credentials |

Use private objects and credentials restricted to object PUT, GET/signing and DELETE in the selected bucket, preferably the staging prefix where the backend supports that restriction. AWS default profiles, instance metadata and ambient AWS keys are not used. The account HTTPS endpoint must be canonical; redirects are rejected. Restart ComfyUI after changing its launch environment. Configuration identity is endpoint + region + bucket, hashed without credentials. Rotating credentials for the same bucket preserves cleanup ownership.

Configure a 48-hour expiration rule for openrouter-video/staging/ once in the R2 dashboard. The plugin requires no bucket administration rights and never reads/creates/changes that rule. See [R2 lifecycle setup](https://developers.cloudflare.com/r2/buckets/object-lifecycles/) and [R2 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/). Provider expiration does not promise physical deletion at exactly 48:00.

The plugin generates random object names without source filenames. Signed GET URLs last 24 hours and require no additional headers. Media bytes, paths, storage secrets and signatures are never persisted in the workflow, jobs database or errors. The ledger stores only ownership and cleanup metadata.

## Recovery and cleanup

Generate keeps the existing one-paid-POST claim. Storage failure sends zero Video POSTs. Successful submission is observed with the same job ID. Resume performs no upload and no submit. Expired signed URLs do not permit another generation.

Confirmed completed/failed/cancelled/expired jobs, definite rejections and proven no-submit objects are deleted immediately where possible. A DELETE failure leaves cleanup pending without changing the job result. Unknown submission, unknown remote status and poll interruption retain inputs. Startup, Generate, Resume and terminal transitions retry cleanup; there is no background thread/service. A 48-hour emergency threshold removes exact ledger-owned objects even if job state remains uncertain. The provider lifecycle covers ComfyUI being switched off.

When the bucket/endpoint/region changes, old ledger rows are preserved: cleanup cannot delete into the new configuration. Restore the original local settings to reconcile them, or rely on the old bucket's configured lifecycle. The plugin does not enumerate buckets or issue bulk/prefix deletes.

## Separately approved live smokes

1. **Storage only:** user configures local R2 credentials and its lifecycle; explicitly authorize the synthetic storage smoke. Run tests/manual/native_media_storage_smoke.py --execute. It writes one tiny WAV object, reads its signed HTTPS GET without auth/attribution headers, compares bytes and deletes its exact key. It performs no OpenRouter request. SDK PUT retries cannot exceed three actual sends. Do not report live storage PASS before this completes.
2. **OpenRouter:** use a user-configured capped DEV key and local storage credentials, then explicitly authorize one generation immediately before Queue. Use the synthetic native workflow from browser proof (video + audio + image), select the approved exact model and a supported short duration/resolution, and review the cost estimate against the owner's cap. Queue once, observe the returned job and verify terminal cleanup. No paid retry, alternate model or resubmission is permitted; after interruption use Resume only. The API key spending cap is authoritative; an estimate is not a charge guarantee. Verify the canonical DEV source is refreshed first. Do not present the synthetic browser fixture as authenticated live evidence.

Publication, PR merge and release are outside this package. See [ADR-032](adr/ADR-032-native-media-s3-staging.md).
