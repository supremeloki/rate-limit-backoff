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
    duration: float
    error_summary: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome == "success"


@dataclass
class RetryPolicy:
    max_attempts: int = 5
    base_delay: float = 0.5
    strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    multiplier: float = 2.0
    max_delay: float = 30.0
    jitter_ratio: float = 0.0
    retryable: tuple[type[BaseException], ...] = (Exception,)
    total_time_budget: float | None = None

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise BackoffError("max_attempts must be >= 1")
        if self.base_delay < 0 or self.max_delay < 0:
            raise BackoffError("delays must be >= 0")
        if not 0.0 <= self.jitter_ratio <= 1.0:
            raise BackoffError("jitter_ratio must be in [0, 1]")
        if self.multiplier < 1.0:
            raise BackoffError("multiplier must be >= 1")

    def compute_delay(self, attempt_index: int,
                      rng: Callable[[], float] | None = None) -> float:
        import random

        rng = rng or random.random
        if self.strategy is BackoffStrategy.FIXED:
            raw = self.base_delay
        elif self.strategy is BackoffStrategy.LINEAR:
            raw = self.base_delay * (attempt_index + 1)
        elif self.strategy is BackoffStrategy.EXPONENTIAL:
            raw = self.base_delay * (self.multiplier ** attempt_index)
        else:
            sequence = list(fibonacci_sequence(attempt_index + 1))
            raw = self.base_delay * sequence[-1]
        capped = min(raw, self.max_delay)
        if self.jitter_ratio > 0:
            jitter_span = capped * self.jitter_ratio
            return max(0.0, capped - jitter_span + 2 * jitter_span * rng())
        return capped


class RetryExecutor:
    def __init__(self, policy: RetryPolicy,
                 sleep: Callable[[float], None] | None = None,
                 clock: Callable[[], float] | None = None) -> None:
