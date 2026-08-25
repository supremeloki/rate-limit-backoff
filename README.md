# rate-backoff

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Retry and rate limiting primitives for LLM APIs: four backoff strategies with jitter, a retry executor that distinguishes transient from fatal failures, time budgets, and a token bucket limiter.

## 🚀 Overview

LLM APIs throttle constantly; naive retries make it worse. `rate-backoff` gives you the full toolkit: `FIXED` / `LINEAR` / `EXPONENTIAL` / `FIBONACCI` delay curves, optional bounded jitter (thundering-herd guard), a **retryable vs fatal** exception split (`KeyboardInterrupt` never retried), an overall **time budget** that aborts before attempts exhaust, per-attempt callbacks with structured records, plus a classic **token bucket** limiter with wait-time prediction.

## ✨ Features

- **Four delay strategies:** fixed, linear, exponential, fibonacci — all capped by `max_delay`
- **Bounded jitter:** `jitter_ratio ∈ [0,1]` keeps delays inside a known window
- **Transient/fatal split:** only declared exception types retried; everything else re-raises immediately
- **Time budget:** `total_time_budget` aborts the whole run when exceeded
- **Attempt records:** number, delay, outcome, duration, error summary — feed to metrics
- **Token bucket:** capacity + refill rate, `try_acquire`, `wait_time` forecasting
- **Injectable sleep & clock:** zero real waiting in tests, deterministic budgets
- **Zero dependencies**

## 🚧 Structure

```
rate-limit-backoff/
├── src/rate_backoff/
│   ├── __init__.py
│   └── core.py
├── tests/
│   └── test_core.py
├── README.md
└── pyproject.toml
```

## 📦 Installation

```bash
git clone https://github.com/supremeloki/rate-limit-backoff.git
cd rate-limit-backoff
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## 📋 Requirements

- Python 3.11+
- No runtime dependencies

## 🏃 Quick Start

```python
from rate_backoff import BackoffStrategy, RetryExecutor, RetryPolicy

policy = RetryPolicy(
    max_attempts=5,
    base_delay=0.5,
    strategy=BackoffStrategy.EXPONENTIAL,
    jitter_ratio=0.2,
    total_time_budget=30.0,
)
executor = RetryExecutor(policy)

result = executor.run(call_llm_api)

from rate_backoff import TokenBucketRateLimiter
bucket = TokenBucketRateLimiter(capacity=60, refill_per_second=10)
if bucket.try_acquire():
    ...
```

## 🔧 Error Handling

```text
BackoffError
├── AttemptsExhaustedError      # .last_error carries the final underlying failure
├── RetryBudgetExceededError    # wall-clock budget spent before attempts ran out
└── invalid policy/bucket config
```

Fatal exceptions propagate unchanged — never wrapped.

## 🧪 Testing

```bash
pytest tests/ -v
```

## 📝 Code Quality

- Full type hints (`X | None` style), frozen policies/records
- Zero comments — names carry the meaning
- All four strategies' curves asserted numerically; fatal-vs-retryable boundary covered

## 📄 License

MIT — see [LICENSE](LICENSE).

## 👤 Author

**Kooroush Masoumi** - [kooroushmasoumi@gmail.com](mailto:kooroushmasoumi@gmail.com)

---

⭐ Star this repo if you find it useful!
