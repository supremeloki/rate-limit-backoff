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
        self._policy = policy
        self._sleep = sleep or time.sleep
        self._clock = clock or time.monotonic

    def run(self, operation: Callable[[], Any],
            on_attempt: Callable[[AttemptRecord], None] | None = None) -> Any:
        started = self._clock()
        last_error: BaseException | None = None
        for attempt_index in range(self._policy.max_attempts):
            if (self._policy.total_time_budget is not None
                    and self._clock() - started >= self._policy.total_time_budget):
                raise RetryBudgetExceededError(
                    f"time budget {self._policy.total_time_budget}s exhausted"
                )
            delay = self._policy.compute_delay(attempt_index) \
                if attempt_index > 0 else 0.0
            op_started = self._clock()
            try:
                result = operation()
                duration = self._clock() - op_started
                record = AttemptRecord(
                    attempt_number=attempt_index + 1,
                    delay_before=delay,
                    outcome="success",
                    duration=round(duration, 4),
                )
                if on_attempt:
                    on_attempt(record)
                return result
            except self._policy.retryable as exc:
                last_error = exc
                duration = self._clock() - op_started
                record = AttemptRecord(
                    attempt_number=attempt_index + 1,
                    delay_before=delay,
                    outcome="retryable-failure",
                    duration=round(duration, 4),
                    error_summary=f"{type(exc).__name__}: {exc}",
                )
                if on_attempt:
                    on_attempt(record)
                if delay > 0:
                    self._sleep(delay)
            except BaseException as exc:
                record = AttemptRecord(
                    attempt_number=attempt_index + 1,
                    delay_before=0.0,
                    outcome="fatal",
                    duration=self._clock() - op_started,
                    error_summary=f"{type(exc).__name__}: {exc}",
                )
                if on_attempt:
                    on_attempt(record)
                raise
        raise AttemptsExhaustedError(self._policy.max_attempts, last_error)


class TokenBucketRateLimiter:
    def __init__(self, capacity: int, refill_per_second: float) -> None:
        if capacity < 1 or refill_per_second <= 0:
            raise BackoffError("capacity >= 1 and positive refill required")
        self.capacity = capacity
        self.refill_rate = refill_per_second
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(float(self.capacity),
                          self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def try_acquire(self, tokens: int = 1) -> bool:
        if tokens > self.capacity:
            raise BackoffError("requested tokens exceed bucket capacity")
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def wait_time(self, tokens: int = 1) -> float:
        self._refill()
        deficit = tokens - self.tokens
        if deficit <= 0:
            return 0.0
        return round(deficit / self.refill_rate, 4)
