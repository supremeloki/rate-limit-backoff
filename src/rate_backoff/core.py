from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BackoffError(Exception):
    pass


class AttemptsExhaustedError(BackoffError):
    def __init__(self, attempts: int, last_error: BaseException) -> None:
        super().__init__(f"failed after {attempts} attempts: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


class RetryBudgetExceededError(BackoffError):
    pass


class BackoffStrategy(str, Enum):
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    FIBONACCI = "fibonacci"


def fibonacci_sequence(count: int) -> Iterator[float]:
    first, second = 1.0, 1.0
    for _ in range(max(0, count)):
        yield first
        first, second = second, first + second


@dataclass(frozen=True)
class AttemptRecord:
    attempt_number: int
    delay_before: float
    outcome: str
