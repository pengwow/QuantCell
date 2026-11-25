---
title: 回测详解
description: 统一内核回测、三条执行路径、Walk-Forward 验证与超参优化
---

# 回测详解

## 统一内核（默认路径）

回测默认通过统一内核（Rust 侧 `PyKernel`，内部调 `Kernel::run_history`）执行，与
paper / live 共用同一条 per-bar 主回路，保证语义一致。

```python
from strategy.rust_adapter import RustStrategyAdapter

# 内核实例由 backtest/engine_service.py 按 engine_config['runner'] 统一构造，
# 业务侧只提供 RustStrategyAdapter（BaseStrategy.on_bar → 内核 StrategyHost）
```

三条执行路径由 `engine_config['runner']` 选择，输出同一 `BacktestResult` 契约：

| `runner` | 执行路径 | 说明 |
|----------|----------|------|
| 缺省（`kernel`） | `Kernel` | 默认，统一内核 `run_history` |
| `legacy` | `BacktestRunner` | legacy 编排，冻结保留 |
| `python` | `BacktestLoop` | 纯 Python 回退路径 |

## 放行的数据类型

`data_type ∈ RUST_RUNNER_DATA_TYPES` 时才走 Rust 内核，共 10 类
（均由数据适配器聚合成 bar 形状）：

`kline` / `markPriceKlines` / `indexPriceKlines` / `premiumIndexKlines` /
`aggTrades` / `trades` / `bookDepth` / `bookTicker` / `fundingRate` /
`openInterest`

不在放行集合内的 `data_type` 自动退回 `BacktestLoop`（Python 路径）。

!!! warning "两个语义边界"

    - `fundingRate` 作为 `data_type` 是 DerivAdapter 产出的**特征列**，
      不是 `funding_by_symbol` 的资金费结算通道，混用会导致双件记费
    - `bookDepth` / `bookTicker` 聚合出的是 mid-price **合成价**，不是可撮合盘口

## 多品种

多品种按「每品种独立跑一个内核」执行，与 `BacktestLoop` 每品种独立资金池的
口径一致；跨品种聚合在 Python 侧完成。

## 永续与保证金

- `settle` 由 `market` 推导：`cm` → 币本位（coin margin），其余 → U 本位（usd margin）
- `contract_size` 通过 `engine_config['contract_size']` 设置，默认 `1.0`
- 引擎尚未把乘数计入名义价值 / 盈亏，**币本位账务仍是近似**

## CLI 回测

```bash
quantcell backtest run \
  -s dual_ma \
  --symbols BTCUSDT \
  --timeframes 1h \
  --initial-capital 100000 \
  --trading-mode spot
```

`-s` 为策略名（`quantcell strategy list` 查看），支持逗号分隔多品种多周期。

## 结果契约

`BacktestResult` 字段（三条路径一致）：

```text
total_pnl / total_orders / fills / final_nav / max_drawdown /
sharpe_ratio / trades / equity_curve ...
```

Python 回测示例（详细用法见 `backend/backtest/README.md`）：

```python
from backtest.engine_service import EventDrivenBacktestService
from backtest.data_provider import BacktestDataProvider
from strategy.templates.dual_ma import DualMAStrategy

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

## Walk-Forward 验证

滚动窗口回测（训练窗 → 测试窗滚动前移）防止过拟合：

- **训练窗**用于拟合 / 优化参数
- **测试窗**只做一次前向验证
- 逐窗拼接测试段，得到样本外综合表现

适用于参数敏感的策略（动量、均值回归、RL 等）。

## HPO 超参优化

基于 **Optuna** 的超参数搜索：

- 定义参数空间与目标（如 Sharpe、Calmar）
- 引擎自动多轮回测，收敛到最优参数组
- 建议 HPO 结果再用 Walk-Forward 做一次独立验证，双重防过拟合

## 一致性保障

- `tests/unit/backtest/test_rust_runner_parity.py` 守护 Python ↔ legacy 逐字段一致
- Kernel 与 legacy 的逐 bar 语义一致性由内核 crate 单测与 shadow oracle 守护
