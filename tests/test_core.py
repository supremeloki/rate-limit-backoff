import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from rate_backoff import (
    AttemptsExhaustedError,
    BackoffError,
    BackoffStrategy,
    RetryBudgetExceededError,
    RetryExecutor,
    RetryPolicy,
    TokenBucketRateLimiter,
)


def no_sleep(_seconds: float) -> None:
    pass


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_policy_validation():
    with pytest.raises(BackoffError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(BackoffError):
        RetryPolicy(jitter_ratio=2.0)
    with pytest.raises(BackoffError):
        RetryPolicy(multiplier=0.5)


@pytest.mark.parametrize("strategy,expected", [
    (BackoffStrategy.FIXED, [1.0, 1.0, 1.0, 1.0]),
    (BackoffStrategy.LINEAR, [1.0, 2.0, 3.0, 4.0]),
    (BackoffStrategy.EXPONENTIAL, [1.0, 2.0, 4.0, 8.0]),
])
def test_delay_strategies(strategy, expected):
    policy = RetryPolicy(base_delay=1.0, strategy=strategy)
    delays = [policy.compute_delay(i) for i in range(4)]
    assert delays == expected


def test_fibonacci_delays():
    policy = RetryPolicy(base_delay=1.0, strategy=BackoffStrategy.FIBONACCI)
    assert policy.compute_delay(0) == 1.0
    assert policy.compute_delay(1) == 1.0
    assert policy.compute_delay(2) == 2.0
    assert policy.compute_delay(3) == 3.0


def test_max_delay_caps_exponential_growth():
    policy = RetryPolicy(base_delay=1.0, multiplier=4.0, max_delay=8.0,
                         strategy=BackoffStrategy.EXPONENTIAL)
    assert policy.compute_delay(10) == 8.0


def test_jitter_stays_within_bounds():
    policy = RetryPolicy(base_delay=10.0, jitter_ratio=0.2)
    for index in range(20):
        delay = policy.compute_delay(0, rng=lambda: 0.5)
        assert delay <= 12.0 + 1e-9


def test_success_on_first_attempt():
    executor = RetryExecutor(RetryPolicy(), sleep=no_sleep)
    assert executor.run(lambda: 42) == 42


def test_retry_until_success():
    calls = {"count": 0}

    def flaky() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise ConnectionError("transient")
        return "recovered"

    executor = RetryExecutor(
        RetryPolicy(max_attempts=5, base_delay=0.1), sleep=no_sleep,
    )
    assert executor.run(flaky) == "recovered"
    assert calls["count"] == 3


def test_attempts_exhausted_carries_last_error():
    executor = RetryExecutor(
        RetryPolicy(max_attempts=2), sleep=no_sleep,
    )
    with pytest.raises(AttemptsExhaustedError) as excinfo:
        executor.run(lambda: (_ for _ in ()).throw(ValueError("always")))
    assert "always" in str(excinfo.value.last_error)


def test_non_retryable_reraises_immediately():
    attempts: list[int] = []

    def fatal() -> None:
        attempts.append(1)
        raise KeyboardInterrupt("user abort")

    executor = RetryExecutor(
        RetryPolicy(max_attempts=5, retryable=(ConnectionError,)),
        sleep=no_sleep,
    )
    with pytest.raises(KeyboardInterrupt):
        executor.run(fatal)
    assert len(attempts) == 1


