"""Compatibility aliases; reviewed manifest is the sole enrichment mechanism."""

from openrouter_video.evidence_registry import enrich_capabilities as apply_capability_overlay
from openrouter_video.evidence_registry import preferred_method as preferred_inference_method

__all__ = ("apply_capability_overlay", "preferred_inference_method")
