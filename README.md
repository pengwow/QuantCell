# QuantCell — AI-Native Quantitative Trading System

English | [简体中文](README_CN.md)

[Live Demo](https://demo.quantcell.top/chart) | [Homepage](https://quantcell.top)

## 1. Overview

QuantCell is an AI-native quantitative trading system built on a Rust core trading engine, with FastAPI as the service framework and React + TypeScript on the frontend. It covers the full workflow from strategy development and backtest validation to live deployment.

Core philosophy: **make quantitative trading simple, efficient, and intelligent** — describe a strategy in natural language, and AI generates the code and validates it with backtests.

The system follows a **unified kernel architecture**: backtest, paper trading, and live trading share the same per-bar main loop driven by the Rust kernel. Modes differ only in the data pump and execution sink wiring, which guarantees behavioral consistency between backtests and live trading.

## 2. Desktop Client

Desktop builds are available for macOS / Windows / Linux. The desktop app is a Tauri 2 shell reusing the same `frontend/` code, with the local `backend` (FastAPI + Rust core) packaged via PyInstaller and launched as a sidecar process. `local` mode requires no login and reaches the app directly; `remote` mode connects to a remote server.

| Platform | Architecture | Package |
|----------|--------------|---------|
| macOS (Apple Silicon M-series) | aarch64 | `QuantCell_<ver>_aarch64.dmg` |
| macOS (Intel) | x86_64 | `QuantCell_<ver>_x64.dmg` |
| Windows | x86_64 | `QuantCell_<ver>_x64.msi` / `.exe` |
| Linux | x86_64 | `quantcell_<ver>_amd64.deb` / `.AppImage` |

- Download location: GitHub Actions **artifacts** (`quantcell-desktop-*`), generated automatically on `v*` tags
- Unsigned binaries: on macOS right-click → Open on first launch; on Windows click "Run anyway" when prompted about an unknown publisher
- CI build workflow: `.github/workflows/desktop-build.yml`, triggered by manual `workflow_dispatch` or `v*` tags

> See [desktop/README.md](desktop/README.md) for detailed desktop development and packaging instructions.

## 3. Key Features

### 🤖 AI Intelligence

- **Natural-language strategy generation**: describe a trading idea in plain language, AI generates executable strategy code
- **Chain-of-thought reasoning**: multi-step strategy and indicator generation with explainable, traceable logic
- **Code quality self-check**: automatic syntax and runtime-safety validation, unsafe code rejected
- **Intelligent Agent**: an AI agent with memory and tool calling for multi-turn conversations and task orchestration
- **LLM decision recording & replay**: LLM strategies replay recorded decisions during backtests without real LLM calls

### ⚡ Rust High-Performance Engine

- **Rust core**: unified kernel architecture
- **Unified main loop**: backtest / paper / live share the same per-bar orchestration for consistent semantics
- **Multi-data-type backtests**: adapters for klines, derivatives data (funding rate etc.), order book, and trades
- **Walk-forward validation**: rolling-window backtests to prevent overfitting
- **HPO**: built-in hyperparameter optimization with Optuna

### 🎯 Reinforcement Learning

- **Gymnasium trading environment**: built-in trading Gym environment
- **Stable-Baselines3**: supports mainstream algorithms such as PPO / SAC / DQN
- **Full lifecycle**: train → backtest → evaluate → retrain, with walk-forward validation

### 🔌 Plugin System

- **Plugin installation & management**: install, pack, and manage plugins via the `quantcell plugin` command
- **Event bus**: plugins communicate through a unified event bus
- **Security sandbox**: plugins run in a restricted sandbox to protect the main process

### 🛡️ Risk & Compliance

- **Encrypted credential storage**: exchange API keys stored encrypted, managed via `quantcell account`
- **Risk engine**: trading risk monitoring, stop-loss and position controls
- **Multilingual UI**: built-in i18n support

### 📊 Complete Data Ecosystem

- **Multiple exchanges**: Binance (live / paper / archive) and OKX adapters
- **Real-time market data**: WebSocket subscription, distribution, and persistence
- **Parquet storage**: columnar storage for efficient reads and writes
- **Data quality checks**: missing-value detection, automatic re-download, and archive repair

### 🎨 Modern Frontend

- **React 19 + TypeScript + Vite 8**: type-safe component-based development
- **Ant Design 6**: enterprise-grade UI components
- **KLineCharts / ECharts**: professional candlestick and indicator charts
- **Zustand**: lightweight global state management
- **i18n**: seamless Chinese/English switching (i18next)
- **Monaco editor**: built-in code editor

## 4. Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  Frontend (React + TypeScript)            │
│     Ant Design 6 · KLineCharts · Zustand · i18n · Tauri   │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼───────────────────────────────┐
│                API Layer (FastAPI, /api/v1)               │
│   CORS · Auth · Error handling · Capabilities · Metrics   │
└──────┬───────────────┬────────────────┬───────────────────┘
       │               │                │
       ▼               ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Strategy &  │  │ Live/Real-  │  │ Data        │
│ Backtest    │  │ time        │  │ Collection  │
│ strategy/   │  │ realtime/   │  │ collector/  │
│ backtest/   │  │ worker/     │  │ quality/    │
│ factor/rl   │  │ credentials │  │ marketdata/ │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       ▼                ▼                ▼
┌──────────────────────────────────────────────────────────┐
│           Rust kernel · Binance / OKX · DuckDB           │
│     Backtest / paper / live share one per-bar main loop   │
└──────────────────────────────────────────────────────────┘
       ▲                ▲                ▲
┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐
│   Agent     │  │    CLI      │  │   Plugins   │
│  agent/     │  │  quantcell  │  │  plugins/   │
│  research/  │  │ 15 groups   │  │  Event bus  │
└─────────────┘  └─────────────┘  └─────────────┘
```

## 5. Tech Stack

| Category | Technology |
|----------|------------|
| Backend language | Python 3.14 |
| Web framework | FastAPI 0.136 (uvicorn) |
| Trading engine | Rust core (PyO3, path dependency) |
| Database | DuckDB 1.4 + Parquet + SQLAlchemy 2 + Alembic |
| Data processing | Pandas 2.3 / PyArrow 22 |
| Reinforcement learning | Gymnasium 1.3 + Stable-Baselines3 2.9 |
| CLI | Typer 0.20 |
| Frontend | React 19 + TypeScript 5.9 + Vite 8 |
| UI components | Ant Design 6 + TailwindCSS 4 |
| Charts | KLineCharts 10 + ECharts 5.5 |
| State management | Zustand 5 |
| Internationalization | i18next / react-i18next |
| Desktop | Tauri 2 + PyInstaller (backend sidecar) |
| Package management | uv (backend) / bun (frontend) |
| Code style | ruff (lint + format) |
| Testing | pytest 9 + coverage (coverage baseline 57%) |

## 6. Quick Start

### Prerequisites

| Component | Version |
|-----------|---------|
| Python | 3.14 |
| uv | latest |
| bun | latest |

> Desktop development also requires the Rust toolchain (Tauri 2); see [desktop/README.md](desktop/README.md).

### One-click install & start

```bash
git clone https://github.com/pengwow/quantcell.git
cd quantcell
bash scripts/install.sh --minimal   # installs uv/bun toolchains, frontend & backend deps, then starts
```

`scripts/install.sh` supports three modes: `--minimal` (minimal deps) / `--full` (full deps) / `--extra <pkg>` (optional dependency groups).

You can also manage dev services via the Makefile:

```bash
make dev-start      # start frontend & backend dev services
make dev-status     # check running status
make dev-stop       # stop services
```

### Manual installation

**Backend**

```bash
cd backend
uv sync                        # install deps and generate the quantcell CLI entry
uv run python init_db.py       # initialize the database
```

**Frontend**

```bash
cd frontend
bun install
```

### Start services

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

API docs: `http://localhost:8000/docs`

Frontend (dev mode):

```bash
cd frontend
bun run dev
```

## 7. CLI Usage

Running `uv sync` generates the `quantcell` command with 15 command groups:

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
   backtest    QuantCell backtest tool (event-driven Rust engine)
   data        Data management CLI
```

> The `quantcell` executable lives in the Python environment's bin directory (e.g. `backend/.venv/bin/quantcell`) and can be used from any directory after `uv sync`.

### Command cheat sheet

| Task | Command |
|------|---------|
| List strategies | `quantcell strategy list` |
| Generate strategy with AI | `quantcell strategy generate --requirement "buy on dual MA golden cross" --name my_strategy` |
| Run a backtest | `quantcell backtest run -s dual_ma --symbols BTCUSDT --timeframes 1h` |
| Download market data | `quantcell data download -s BTCUSDT -i 1d` |
| Data quality check | `quantcell data quality check --start 20240101 --end 20241231` |
| Import from CSV | `quantcell data import csv <file>` |
| Fetch market data | `quantcell market fetch --symbol BTCUSDT --interval 1h` |
| Train an RL model | `quantcell rl train -s BTCUSDT -a ppo -t 100000 -r sharpe` |
| Full RL lifecycle | `quantcell rl lifecycle -s BTCUSDT` |
| Start a worker | `quantcell worker start <worker_id>` |
| List workers | `quantcell worker list-workers` |
| List accounts | `quantcell account list` |
| Migrate database | `quantcell migrate -y` |
| Run unit tests | `quantcell tests main --unit` |
| Install a plugin | `quantcell plugin install x.zip` |

## 8. Core Usage

### 1. Generate strategies with AI

Use the frontend chat UI, or generate directly from the command line:

```bash
quantcell strategy generate \
  --requirement "dual moving-average trend following: fast 10 days, slow 30 days, buy on golden cross, sell on death cross" \
  --name dual_ma
```

The system automatically: understands the requirement → generates code → validates safety → runs a backtest → outputs a report.

### 2. Run a backtest

CLI (`-s` is the strategy name; run `quantcell strategy list` to see available strategies):

```bash
quantcell backtest run \
  -s dual_ma \
  --symbols BTCUSDT \
  --timeframes 1h \
  --initial-capital 100000 \
  --trading-mode spot
```

Python (see [backend/backtest/README.md](backend/backtest/README.md) for details):

```python
from backtest.engine_service import EventDrivenBacktestService
from backtest.data_provider import BacktestDataProvider

provider = BacktestDataProvider()               # data provider (Parquet/CSV)
service = EventDrivenBacktestService(provider)
result = service.run_backtest(
    strategy_name="dual_ma",
    strategy_params={"fast": 10, "slow": 30},
    symbols=["BTCUSDT"],
    timeframes=["1h"],
    engine_config={"initial_capital": 100_000},
    data_type="kline",
    market="spot",
)
print(result)  # dict with return, max drawdown, fills, and other metrics
```

Backtests run on the unified Rust kernel by default; three execution paths (unified kernel / legacy engine / Python fallback) are selected via `engine_config['runner']`, all producing the same `BacktestResult` contract.

### 3. Reinforcement learning training

```bash
quantcell rl train \
    -s BTCUSDT \
    -a ppo \
    -t 100000 \
    -r sharpe

# One-shot lifecycle: train → backtest → evaluate → retrain
quantcell rl lifecycle -s BTCUSDT --train-steps 30000 --retrain-steps 10000
```
