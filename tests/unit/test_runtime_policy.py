"""Exact Phase-4 operation and timeout policy."""

from openrouter_video.policy import Operation, RuntimePolicy


def test_operation_matrix_and_timeouts_are_exact() -> None:
    runtime = RuntimePolicy()
    expected = {
        Operation.DISCOVERY: ("GET", "/api/v1/videos/models", (10, 10, 30, 10, None)),
        Operation.SUBMIT: ("POST", "/api/v1/videos", (10, 30, 60, 10, None)),
        Operation.POLL: ("GET", "/api/v1/videos/{job_id}", (10, 10, 30, 10, None)),
        Operation.CONTENT: (
            "GET",
            "/api/v1/videos/{job_id}/content?index=0",
            (10, 10, 60, 10, 1200),
        ),
    }

    for operation, (method, path, timeout_values) in expected.items():
        policy = runtime.for_operation(operation)
        timeout = policy.timeout
        assert (policy.method, policy.path_template) == (method, path)
        assert (
            timeout.connect_seconds,
            timeout.write_seconds,
            timeout.read_seconds,
            timeout.pool_seconds,
            timeout.wall_clock_seconds,
        ) == timeout_values

    assert runtime.max_connections == 10
    assert runtime.max_keepalive_connections == 5
