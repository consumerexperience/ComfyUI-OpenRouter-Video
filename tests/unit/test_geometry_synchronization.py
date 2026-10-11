from openrouter_video.geometry import geometry_profile, wire_geometry
from openrouter_video.models import GenerationRequest


def test_safe_rational_aspects_never_promote_resolution_tiers() -> None:
    profile = geometry_profile(
        ["720p", "4K"], ["16:9", "9:16", "4:3"], ["1280x720", "720x1280", "854x480", "1112x834"]
    )
    assert isinstance(profile["tuples"], list)
    tuples = profile["tuples"]
    assert [entry["aspect_ratio"] for entry in tuples] == ["16:9", "9:16", "16:9", "4:3"]
    assert all(entry["resolution"] is None for entry in tuples)
    assert all(entry["confidence"] == "SAFE_DERIVED" for entry in tuples)


def test_ambiguous_rounding_and_unmatched_ratios_remain_unknown() -> None:
    profile = geometry_profile(["720p"], ["16:9", "17:9"], ["1x1", "100x100"])
    assert isinstance(profile["tuples"], list)
    assert all(entry["confidence"] == "UNKNOWN" for entry in profile["tuples"])


def test_explicit_complete_structured_tuple_is_the_only_tier_authority() -> None:
    profile = geometry_profile(
        ["720p"],
        ["16:9"],
        ["1280x720"],
        [
            {
                "axes": ["resolution", "aspect_ratio", "size"],
                "complete": True,
                "when": {},
                "allowed": [
                    {"resolution": ["720p"], "aspect_ratio": ["16:9"], "size": ["1280x720"]}
                ],
            }
        ],
    )
    assert isinstance(profile["tuples"], list)
    assert any(
        entry["confidence"] == "CONFIRMED" and entry["resolution"] == "720p"
        for entry in profile["tuples"]
    )


def test_ui_authority_never_leaks_into_openrouter_payload() -> None:
    for authority in ("NORMALIZED", "EXACT"):
        resolution, aspect, size = wire_geometry(authority, "720p", "16:9", "1280x720")
        payload = GenerationRequest(
            model="test/model", prompt="test", resolution=resolution, aspect_ratio=aspect, size=size
        ).to_openrouter_payload()
        assert "geometry_authority" not in payload
        assert not ("size" in payload and ("resolution" in payload or "aspect_ratio" in payload))
        assert ("size" in payload) == (authority == "EXACT")
