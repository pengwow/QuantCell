---
title: Backtesting
description: Unified-kernel backtests, three execution paths, walk-forward validation, and HPO
---

# Backtesting

## Unified kernel (default path)

Backtests run on the unified kernel (Rust-side `PyKernel`, which calls
`Kernel::run_history`) by default — the same per-bar main loop that paper / live
use, guaranteeing consistent semantics.

```python
from strategy.rust_adapter import RustStrategyAdapter

# The kernel instance is built by backtest/engine_service.py according to
# engine_config['runner']; business code only supplies RustStrategyAdapter
# (BaseStrategy.on_bar → kernel StrategyHost).
```

Three execution paths are selected via `engine_config['runner']`, all
producing the same `BacktestResult` contract:

| `runner` | Path | Notes |
|----------|------|-------|
| default (`kernel`) | `worker.Kernel` | default, unified kernel `run_history` |
| `legacy` | `worker.BacktestRunner` | legacy orchestration, frozen but kept |
| `python` | `BacktestLoop` | pure-Python fallback |

## Admitted data types

The Rust kernel accepts `data_type ∈ RUST_RUNNER_DATA_TYPES`, 10 types in
total (all aggregated into bar shape by data adapters):

`kline` / `markPriceKlines` / `indexPriceKlines` / `premiumIndexKlines` /
`aggTrades` / `trades` / `bookDepth` / `bookTicker` / `fundingRate` /
`openInterest`

Any other `data_type` automatically falls back to `BacktestLoop` (Python path).

!!! warning "Two semantic boundaries"

    - `fundingRate` as a `data_type` is a **feature column** produced by
      DerivAdapter, not the funding settlement channel of `funding_by_symbol`;
      mixing both double-charges funding
    - `bookDepth` / `bookTicker` aggregate into a mid-price **synthetic quote**,
      not a matchable order book

## Multi-symbol

Multi-symbol runs execute one kernel per symbol, matching `BacktestLoop`'s
per-symbol cash pool semantics; cross-symbol aggregation happens on the
Python side.

## Perpetuals & margin

- `settle` is derived from `market`: `cm` → coin margin, otherwise → usd margin
- `contract_size` is set via `engine_config['contract_size']`, default `1.0`
- The engine does not yet include the multiplier in notional / PnL —
  **coin-margin accounting is approximate**

## CLI backtest

```bash
quantcell backtest run \
  -s dual_ma \
  --symbols BTCUSDT \
  --timeframes 1h \
  --initial-capital 100000 \
  --trading-mode spot
```

`-s` is the strategy name (see `quantcell strategy list`); comma-separated
multi-symbol / multi-timeframe lists are supported.

## Result contract

`BacktestResult` fields (identical across all three paths):

```text
total_pnl / total_orders / fills / final_nav / max_drawdown /
sharpe_ratio / trades / equity_curve ...
```

Python backtest example (details in `backend/backtest/README.md`):

```python
from backtest.engine_service import EventDrivenBacktestService
from backtest.data_provider import BacktestDataProvider

service = EventDrivenBacktestService(BacktestDataProvider())
result = service.run_backtest(
    strategy_name="dual_ma",
    strategy_params={"fast": 10, "slow": 30},
    symbols=["BTCUSDT"],
    timeframes=["1h"],
    engine_config={"initial_capital": 100_000},
    data_type="kline",
    market="spot",
)
print(result)
```

## Walk-forward validation

Rolling-window backtests (training window → test window, rolling forward)
guard against overfitting:

- **Training window** fits / optimizes parameters
- **Test window** performs a single forward validation
- Test segments are stitched across windows for out-of-sample performance

Recommended for parameter-sensitive strategies (momentum, mean reversion, RL).

## HPO

Hyperparameter search built on **Optuna**:

- Define the parameter space and objective (e.g. Sharpe, Calmar)
- The engine runs multiple backtest rounds and converges to the best parameter set
- Validate HPO results once more with walk-forward — double protection against overfitting

## Consistency guarantees

- `tests/unit/backtest/test_rust_runner_parity.py` guards Python ↔ legacy
  field-by-field equality
- Kernel vs legacy per-bar semantic consistency is guarded by kernel crate
  unit tests and the shadow oracle
