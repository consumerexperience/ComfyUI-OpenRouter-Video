import pytest

from openrouter_video.capabilities import RequestValidator
from openrouter_video.models import GenerationRequest


def test_normalized_geometry_serializes_only_normalized_fields() -> None:
    request = GenerationRequest(
        model="test/model", prompt="test", resolution="720p", aspect_ratio="16:9"
    )
    RequestValidator().validate_shape(request)
    payload = request.to_openrouter_payload()
    assert payload["resolution"] == "720p"
    assert payload["aspect_ratio"] == "16:9"
    assert "size" not in payload


def test_exact_geometry_serializes_only_explicit_pixels() -> None:
    request = GenerationRequest(model="test/model", prompt="test", size="1280x720")
    RequestValidator().validate_shape(request)
    payload = request.to_openrouter_payload()
    assert payload["size"] == "1280x720"
    assert "resolution" not in payload
    assert "aspect_ratio" not in payload


@pytest.mark.parametrize(
    "normalized",
    [
        {"resolution": "720p"},
        {"aspect_ratio": "16:9"},
        {"resolution": "720p", "aspect_ratio": "16:9"},
    ],
)
def test_ambiguous_geometry_never_reaches_serializer(normalized: dict[str, str]) -> None:
    request = GenerationRequest(
        model="test/model",
        prompt="test",
        size="1280x720",
        resolution=normalized.get("resolution"),
        aspect_ratio=normalized.get("aspect_ratio"),
    )
    with pytest.raises(ValueError, match="Ambiguous geometry"):
        request.to_openrouter_payload()
    with pytest.raises(Exception, match="Exact size cannot be combined"):
        RequestValidator().validate_shape(request)
