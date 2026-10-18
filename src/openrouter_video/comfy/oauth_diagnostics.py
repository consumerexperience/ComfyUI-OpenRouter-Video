"""Bounded process-memory categories only; no request data or durable logging."""

from collections import deque
from enum import Enum
from threading import Lock


class Outcome(str, Enum):
    SUCCESS = "SUCCESS"
    DUPLICATE = "DUPLICATE"
    RECEIVER_CLOSING = "RECEIVER_CLOSING"
    DEADLINE = "DEADLINE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_CALLBACK_SHAPE = "INVALID_CALLBACK_SHAPE"
    STATE_MISMATCH = "STATE_MISMATCH"
    ENVIRONMENT_MANAGED = "ENVIRONMENT_MANAGED"
    EXCHANGE_FAILED = "EXCHANGE_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    STORE_FAILED = "STORE_FAILED"
    COMPLETION_FAILED = "COMPLETION_FAILED"
    UNEXPECTED_FAILURE = "UNEXPECTED_FAILURE"


class CallbackOutcomes:
    def __init__(self) -> None:
        self._items: deque[str] = deque(maxlen=32)
        self._lock = Lock()

    def record(self, category: Outcome) -> None:
        if not isinstance(category, Outcome):
            raise TypeError("Only predefined callback categories are accepted")
        with self._lock:
            self._items.append(category.value)

    def snapshot(self) -> list[str]:
        with self._lock:
            return list(self._items)


callback_outcomes = CallbackOutcomes()
