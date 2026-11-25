---
title: Home
description: QuantCell — AI-native quantitative trading system official documentation
---

# QuantCell

**QuantCell** is an AI-native quantitative trading system built on a Rust core
trading engine, with FastAPI as the service framework and React + TypeScript on
the frontend. It covers the full workflow from strategy development and backtest
validation to live deployment.

Core philosophy: **make quantitative trading simple, efficient, and
intelligent** — describe a strategy in natural language, and AI generates the
code and validates it with backtests.

[Get started](getting-started/installation.md){ .md-button .md-button--primary }
[Live demo](https://demo.quantcell.top/chart){ .md-button }

---

## Key Features

### 🤖 AI Intelligence

- **Natural-language strategy generation**: describe a trading idea in plain language, AI generates executable strategy code
- **Chain-of-thought reasoning**: multi-step strategy and indicator generation with explainable, traceable logic
- **Code quality self-check**: automatic syntax and runtime-safety validation, unsafe code rejected
- **Intelligent Agent**: memory and tool calling, multi-turn conversations and task orchestration
- **LLM decision recording & replay**: LLM strategies replay recorded decisions during backtests without real LLM calls

### ⚡ Rust High-Performance Engine

- **Rust core**: unified kernel architecture
- **Unified main loop**: backtest / paper / live share the same per-bar orchestration for consistent semantics
- **Multi-data-type backtests**: adapters for klines, derivatives data (funding rate etc.), order book, and trades
- **Walk-forward validation**: rolling-window backtests to prevent overfitting
- **HPO**: built-in hyperparameter optimization with Optuna

### 🎯 Reinforcement Learning

- **Gymnasium trading environment**: built-in trading Gym environment
- **Stable-Baselines3**: mainstream algorithms such as PPO / SAC / DQN
- **Full lifecycle**: train → backtest → evaluate → retrain, with walk-forward validation

### 🛡️ Risk & Compliance

- **Encrypted credential storage**: exchange API keys stored encrypted, managed via `quantcell account`
- **Risk engine**: trading risk monitoring, stop-loss and position controls
- **Multilingual UI**: built-in i18n support

### 📊 Complete Data Ecosystem

- **Multiple exchanges**: Binance (live / paper / archive) and OKX adapters
- **Real-time market data**: WebSocket subscription, distribution, and persistence
- **Parquet storage**: columnar storage for efficient reads and writes
- **Data quality checks**: missing-value detection, automatic re-download, and archive repair

### 🔌 Plugin System

- **Plugin installation & management**: install, pack, and manage plugins via the `quantcell plugin` command
- **Event bus**: plugins communicate through a unified event bus
- **Security sandbox**: plugins run in a restricted sandbox to protect the main process

### 🎨 Modern Frontend

- **React 19 + TypeScript + Vite 8**: type-safe component-based development
- **Ant Design 6**: enterprise-grade UI components
- **KLineCharts / ECharts**: professional candlestick and indicator charts
- **Monaco editor**: built-in code editor
- **Tauri 2 desktop**: cross-platform desktop app for macOS / Windows / Linux

---

## Documentation Map

| Section | Contents |
|---------|----------|
| [Getting started](getting-started/installation.md) | Prerequisites, installation, running |
| [Architecture](user-guide/architecture.md) | System layers, unified kernel loop, tech stack |
| [Strategy development](user-guide/strategy-development.md) | AI generation, templates, validation |
| [Backtesting](user-guide/backtesting.md) | Unified kernel, execution paths, walk-forward, HPO |
| [Paper & live trading](user-guide/live-trading.md) | Worker system, execution sinks, credentials |
| [Reinforcement learning](user-guide/rl-training.md) | Trading environment, training, lifecycle |
| [Data ecosystem](user-guide/data.md) | Collection, quality, market data & storage |
| [CLI](modules/cli.md) | Full reference for 15 command groups |
| [REST API](reference/api.md) | `/api/v1` route group reference |
| [WebSocket](reference/websocket.md) | Real-time channel protocol |
| [Best practices](best-practices.md) | Strategy, backtest, deployment, security |
| [Troubleshooting](troubleshooting.md) | Install, runtime, trading issue resolution |
