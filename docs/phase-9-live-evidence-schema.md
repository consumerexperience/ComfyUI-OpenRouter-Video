# Phase 9 live evidence schema

One sanitized record is created per approved case. Credentials, Authorization, user prompts, raw
headers, cookies, user identities, and raw upstream bodies are forbidden.

```json
{
  "schema_version": 1,
  "case_id": "first_frame",
  "commit": "40-hex frozen RC commit",
  "platform": "windows-portable",
  "comfy_version": "v0.37.0",
  "model_id": "bytedance/seedance-2.0-mini",
  "reference_mode": "first_frame",
  "configuration": {
    "duration_seconds": 4,
    "resolution": "480p",
    "aspect_ratio": "16:9",
    "generate_audio": false
  },
  "catalogue_observed_at": "RFC3339 UTC",
  "estimate": {
    "availability": "AVAILABLE or UNAVAILABLE",
    "estimated_cost_usd": "decimal string or null",
    "observed_at": "RFC3339 UTC",
    "provenance": "sanitized Core result",
    "applied_skus": []
  },
  "assets": [],
  "redacted_request_shape": {},
  "operation_id": "non-secret durable operation identity",
  "submit_claim": "claimed once",
  "generation_post_count": 1,
  "job_id": "sanitized upstream job identity",
  "chronology": [],
  "runtime_states": [],
  "same_job_recovery": [],
  "attribution": {
    "sent": true,
    "request_accepted": true,
    "surfaced": "UNKNOWN"
  },
  "output_media": {},
  "actual_cost_usd": null,
  "actual_cost_status": "UNKNOWN",
  "e2e_verdict": "UPSTREAM E2E LIVE VERIFIED",
  "conditioning_observation": "PASS",
  "anomaly_rationale": null
}
```

Transport, attribution, conditioning, billing, and recovery claims are evaluated independently.
Same-job Resume/retrieval must retain the original `job_id` and must record zero new generation
POSTs.
