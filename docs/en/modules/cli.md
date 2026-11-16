---
title: CLI
description: Full reference for the quantcell command line — 15 command groups
---

# CLI

After `uv sync`, the `quantcell` command is generated in the Python
environment's bin directory (e.g. `backend/.venv/bin/quantcell`) and works
from any directory.

```
$ quantcell --help
 Usage: quantcell [OPTIONS] COMMAND [ARGS]...

 QuantCell CLI

 Commands:
   agent       Agent management CLI
   factor      Factor research (analysis/compare/code factors/synthetic factors/LLM mining/snapshot)
   market      Market data CLI
   news        News & market sentiment tools
   plugin      Plugin management CLI
   research    Research module operations
   rl          RL CLI
   web         Web search & scraping tools
   worker      Worker management CLI
   tests       QuantCell test runner
   account     Credential management (add/list/remove)
   migrate     Database migrations (SQLite schema upgrade)
   strategy    Strategy management CLI
   backtest    QuantCell backtest tool (event-driven engine axon-quant)
   data        Data management CLI
```

Every group supports `--help` for full parameters, e.g. `quantcell backtest run --help`.

## Common task cheat sheet

### Strategies

```bash
quantcell strategy list                                    # list strategies
quantcell strategy generate \
  --requirement "buy on dual MA golden cross" --name my_strategy  # AI generation
```

### Backtests

```bash
quantcell backtest run -s dual_ma \
  --symbols BTCUSDT --timeframes 1h \
  --initial-capital 100000 --trading-mode spot
```

### Data

```bash
quantcell data download -s BTCUSDT -i 1d                   # download data
quantcell data quality check --start 20240101 --end 20241231
quantcell data import csv <file>
quantcell market fetch --symbol BTCUSDT --interval 1h
```

### Reinforcement learning

```bash
quantcell rl train -s BTCUSDT -a ppo -t 100000 -r sharpe
quantcell rl lifecycle -s BTCUSDT                          # full lifecycle
```

### Agent & research

```bash
quantcell agent ...            # agent management & multi-turn chat
quantcell factor ...           # factor analysis / compare / LLM mining / snapshot
quantcell research ...         # research operations
quantcell news ...             # news & market sentiment
quantcell web ...              # web search & scraping
```

### Operations

```bash
quantcell worker start <worker_id>        # start a worker
quantcell worker list-workers             # list workers
quantcell account add|list|remove         # credential management (encrypted)
quantcell migrate -y                      # database migration
quantcell tests main --unit               # run unit tests
quantcell plugin install x.zip            # install a plugin
```

## Test runner

`quantcell tests` wraps pytest, targeting the same subsets CI uses:

```bash
quantcell tests main --unit        # unit tests
quantcell tests main               # everything
```

You can also invoke pytest directly:

```bash
cd backend && .venv/bin/python -m pytest tests/ -v
```
