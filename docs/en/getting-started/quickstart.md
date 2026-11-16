---
title: Quickstart
description: A complete walkthrough from zero to backtest in five minutes
---

# Quickstart

This page demonstrates the core loop of QuantCell in minimal steps:
**start services → download data → run a backtest → generate a strategy with AI**.

Prerequisites: [installation](installation.md) is complete (`uv sync` generated
the `quantcell` command, the database is initialized).

## 1. Start services

=== "One command"

    ```bash
    make dev-start     # backend uvicorn + frontend vite, daemonized
    make dev-status    # confirm services are ready
    ```

=== "Manual"

    ```bash
    cd backend && uvicorn main:app --host 0.0.0.0 --port 8000
    cd frontend && bun run dev
    ```

Open the frontend dev URL to see the trading workbench.

## 2. Download market data

```bash
quantcell data download -s BTCUSDT -i 1d
```

`-s` selects the symbol, `-i` the candle interval. The first download pulls
history from the exchange and stores it as Parquet.

Verify data quality:

```bash
quantcell data quality check --start 20240101 --end 20241231
```

## 3. Run a built-in strategy backtest

```bash
quantcell strategy list          # list available strategies (13 built-in templates)
quantcell backtest run \
  -s dual_ma \
  --symbols BTCUSDT \
  --timeframes 1h \
  --initial-capital 100000 \
  --trading-mode spot
```

The output includes total return, max drawdown, fills, and more. Backtests run
on the axon-quant Rust unified kernel by default.

## 4. Generate a strategy with AI

```bash
quantcell strategy generate \
  --requirement "dual moving-average trend following: fast 10 days, slow 30 days, buy on golden cross, sell on death cross" \
  --name dual_ma
```

The system automatically: **understands the requirement → generates code →
validates safety → runs a backtest → outputs a report**. Generated strategies
appear on the frontend "Strategy" page for viewing and editing.

## 5. Train an RL model (optional)

```bash
quantcell rl train -s BTCUSDT -a ppo -t 100000 -r sharpe
```

Parameters: `-a` algorithm (ppo / sac / dqn), `-t` training steps, `-r` reward function.

## 6. Connect an exchange (optional)

```bash
quantcell account add            # interactive API key entry (stored encrypted)
quantcell account list           # list configured credentials
```

Credentials are stored encrypted and never written in plain text or printed to logs.

## Next steps

- [Unified main loop architecture](../user-guide/architecture.md) — why backtest / paper / live stay consistent
- [CLI reference](../modules/cli.md) — cheat sheet for the 15 command groups
- [REST API](../reference/api.md) — backend contract
