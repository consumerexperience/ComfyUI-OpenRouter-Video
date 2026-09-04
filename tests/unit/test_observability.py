"""Safe local observability contract."""

import logging

import pytest

from openrouter_video.observability import log_boundary_event
from openrouter_video.policy import Operation


def test_log_event_contains_only_allowlisted_metadata(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("openrouter-video-test")
    with caplog.at_level(logging.INFO, logger=logger.name):
        log_boundary_event(
            logger,
            operation=Operation.DISCOVERY,
            result="policy_rejected",
            http_status=400,
            attribution_applied=False,
        )

    record = caplog.records[-1]
    assert record.message == "openrouter_boundary"
    assert record.openrouter_operation == "DISCOVERY"  # type: ignore[attr-defined]
    assert record.openrouter_host == "openrouter.ai"  # type: ignore[attr-defined]
    assert record.openrouter_result == "policy_rejected"  # type: ignore[attr-defined]
    assert record.openrouter_http_status == 400  # type: ignore[attr-defined]
    assert record.openrouter_attribution_applied is False  # type: ignore[attr-defined]
    assert "TEST_ONLY_OPENROUTER_KEY_CANARY" not in caplog.text
