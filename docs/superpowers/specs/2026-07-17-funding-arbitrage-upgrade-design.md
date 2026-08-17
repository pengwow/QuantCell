# FundingArbitrage 升级: 真双边现货+合约资金费率套利

**Date:** 2026-07-17
**Status:** Design — Pending user review
**Owner:** QuantCell Core Team
**Target Release:** v2.3.0
**Spec 依据:** §6.3 of `2026-07-16-axon-quant-integration-blueprint.md` + P1-Sprint 2 已交付 8 模板

---

## 1. 背景与目标

### 1.1 背景

P1-Sprint 2 已完成 8 个策略模板（含 `funding_arbitrage`），但**当前 `funding_arbitrage.py` 是"单标的简化版"**：

```python
# 当前实现（backend/strategy/templates/funding_arbitrage.py:33）
def on_bar(self, bar, ctx):
    if bar.get("funding_rate", 0.0) > 0:
        return Action(target_position=-self._position_size, reason="funding > 0")
    if bar.get("funding_rate", 0.0) < 0:
        return Action(target_position=+self._position_size, reason="funding < 0")
    return Action(target_position=0, reason="hold")
```

**问题**：
- funding > 0 时只下 perp 空单，**没同时做多现货对冲** → 不是"套利"而是"单边方向性投机"
- 任何 funding 反转都会触发立刻开仓，**无抗噪**（受 funding 0.001% 量级噪声影响）
- **不累计 funding 现金流**到账户（回测 PnL 缺关键组成项）
- **不支持现货腿**（基类 `Action` 只有 `target_position` 单字段）

### 1.2 目标

把 `funding_arbitrage` 从"披着套利外衣的单边投机"升级为**真双边资金费率套利**：

1. **现货 + 合约双腿同时下单**（funding > 0 → 现货做多 + 合约做空；funding < 0 → 现货做空 + 合约做多）
2. **状态机驱动**（3 状态：FLAT / LONG_FUNDING / SHORT_FUNDING）+ 持续时间计数器抗噪
3. **funding 现金流策略层维护**（`StrategyContext.funding_cash` 字段 + `settle_funding()` 方法）
4. **回测引擎（axon_quant）零侵入**（funding 历史 CSV 注入到 baseline，axon_quant 完全不动）
5. **现货做空门控**（`spot_margin_enabled` 默认 False → 自动降级为单边，避免账户被强平）
6. **新 7 个单元测试 + 3 个集成测试 + 1 个自检脚本**（覆盖入场/退场/反转/降级/现金流）
7. **不动现有 8 模板中其他 7 个**（只升级 funding_arbitrage）
8. **不动 P0-Sprint 已交付部分**（axon_bridge 适配层 / 12 子命令 / 归档数据流）

### 1.3 非目标（明确不做）

- ❌ **不改 axon_quant 源码**（项目硬约束：永远 PyPI 安装，不在 in-tree 改）
- ❌ **不新建 SQL 表**（项目约束：状态纯内存，passive funding 现金流进 ledger 即可）
- ❌ **不实现现货做空真实撮合**（依赖 broker / 借贷 API，仅输出 Action 由 baseline 执行）
- ❌ **不实现 funding watcher 推事件**（已有 funding API 接入，归下一 sprint）
- ❌ **不做多币对组合 funding 套利**（只单 symbol）
- ❌ **不实现手续费 + 滑点建模**（baseline 现有框架已处理，本任务不动）
- ❌ **不做 paper trading 集成**（只到 backtest 自检；实盘 deploy 走 P1-Sprint 2 通用 deployer）
- ❌ **不做前端 UI 改造**（仅 CLI 跑 backtest；UI 进度归 P2 路线）

### 1.4 验收标准（必须全部通过）

1. `FundingArbitrageConfig()` 无参数构造成功（所有新字段有默认值）
2. 现有 3 个 `test_advanced_templates.py` 测试**全部不破坏**（向后兼容）
3. 7 个新单元测试**全部通过**（覆盖 6 个核心场景）
4. 3 个新集成测试**全部通过**（覆盖回测端到端 + funding 注入 + 资金不足降级）
5. `python scripts/check_funding_arb.py` 自检脚本：跑 7 天 BTCUSDT 数据无崩 + `ctx.funding_cash > 0` + 状态机至少进入 LONG_FUNDING 一次 + 双腿仓位 delta < 1e-6
6. 完整回测（axon_quant 跑 BTCUSDT 2024-07 → 2025-07）`total_pnl` 包含 funding_cash 项，**报告路径** `data/source/backtest_baselines/funding_arbitrage_BTCUSDT_2024-07_2025-07.{json,md}` 存在
7. `spot_margin_enabled=False` 配 `funding < -entry_threshold` → Action 中 `spot_target_position == 0` 且 `perp_target != 0`（自动降级）
8. 现有 axon_bridge 47 测试 + archive 117 测试 + 12 子命令全部不破坏
9. `docs/superpowers/CHANGELOG_funding_arb.md` 写出本次变更清单
10. `docs/superpowers/specs/2026-07-17-funding-arbitrage-upgrade-design.md`（本文档）通过用户审

---

## 2. 整体架构

### 2.1 文件改动清单

```
backend/strategy/
├── core/
│   ├── strategy_context.py        # 改：+funding_cash, +spot_close, +spot_symbol, +settle_funding()
│   └── strategy_config.py         # 改：+FundingArbitrageConfig 新字段
├── templates/
│   └── funding_arbitrage.py       # 改：升级为真双边
├── tests/
│   └── test_advanced_templates.py # 改：+7 个新测试

backend/backtest/
├── baseline.py                    # 改：+funding_history_path, +spot_symbol, +每 bar 注入
├── tests/integration/             # 新建
│   └── test_funding_arb_backtest.py
└── fixtures/                      # 新建
    └── funding_history_btcusdt_sample.csv

scripts/
└── check_funding_arb.py           # 新建：端到端自检

data/source/backtest_baselines/    # 新建
└── funding_arbitrage_BTCUSDT_2024-07_2025-07.{json,md}

docs/superpowers/
├── specs/2026-07-17-funding-arbitrage-upgrade-design.md  # 新建（本文档）
├── plans/2026-07-17-funding-arbitrage-upgrade.md         # 新建（实施 plan）
└── CHANGELOG_funding_arb.md                              # 新建
```

### 2.2 模块依赖

```
                ┌─────────────────────────────┐
                │   FundingArbitrage (新)      │
                │   templates/funding_arb.py   │
                └──────────┬──────────────────┘
                           │ uses
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   BaseStrategy     StrategyContext     FundingArbitrageConfig
   (不变)            +funding_cash       (新字段)
                     +settle_funding()
        │                  │                  │
        └──────────┬───────┴──────────────────┘
                   │
                   ▼
        axon_quant BacktestEngine (不变)
        + baseline.py 注入 funding + spot
```

### 2.3 数据流时序图

```
每个 timeframe 闭包:
┌──────────────────────────────────────────────────────────────┐
│ baseline.py:                                                 │
│  1. 读 spot bar (BTCUSDT kline)                              │
│  2. 读 perp bar + funding bar                                │
│     (BTCUSDT-PERP kline + funding_rate from CSV)             │
│  3. ctx.spot_close = spot_bar.close                          │
│  4. ctx.spot_volume = spot_bar.volume                        │
│  5. ctx.position = current perp pos                          │
│  6. strategy.on_bar(perp_bar, ctx)                           │
│     策略内:                                                   │
│     a. ctx.settle_funding(perp_bar.funding_rate,             │
│                            perp_bar.funding_time,            │
│                            abs(perp_position) * perp_close)  │
│        → ctx.funding_cash 累加                                │
│     b. 状态机: hold_counter++ 或 = 0                         │
│     c. if counter >= min_hold_bars:                          │
│          return Action(                                       │
│            perp_target=...,                                  │
│            spot_target=...,                                  │
│            reason="enter_long_funding"                       │
│          )                                                    │
│        else: return HOLD_ACTION                              │
│  7. baseline 执行 Action:                                    │
│     - 调仓 perp 到 perp_target                               │
│     - 调仓 spot 到 spot_target                               │
│  8. ledger 记账: ctx.funding_cash 加到账户净值                │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 模块设计

### 3.1 `StrategyContext` 新增字段（`backend/strategy/core/strategy_context.py`）

```python
@dataclass
class StrategyContext:
    # ... 现有字段（symbol, position, account_equity, positions dict, log 等）...

    # —— 新增：现货腿支持 ——
    spot_symbol: str = ""                 # 现货交易对，如 "BTCUSDT"
    spot_close: float = 0.0              # 当前 timeframe 的 spot close（baseline 注入）
    spot_volume: float = 0.0             # 当前 timeframe 的 spot volume
    spot_target_position: float = 0.0    # 现货目标仓位（action 输出用）

    # —— 新增：funding 现金流 ——
    funding_cash: float = 0.0            # 本策略生命周期累计 funding PnL（USD）
    last_funding_rate: float = 0.0       # 最近一次观察到的 funding rate（decimal）
    last_funding_time: int = 0           # 最近一次 funding 结算时间（毫秒）
    funding_cash_settlement_enabled: bool = True  # 是否累加（生产 True，冒烟测试可关）

    # —— 新增：方法 ——
    def settle_funding(
        self,
        funding_rate: float,
        funding_time: int,
        position_notional: float,
    ) -> float:
        """funding 结算：funding 时刻跨过时累加到 funding_cash。

        Args:
            funding_rate: 本期资金费率（decimal, e.g. 0.0003）
            funding_time: 本期 funding 时间戳（毫秒）
            position_notional: 当前 perp 持仓名义价值（USD，正=多头）

        Returns:
            本次累加的 cash_delta（USD）；多空符号约定如下

        公式:
            cash_delta = -funding_rate * position_notional
            持仓多头 + funding > 0 → 付出 funding（cash_delta < 0）
            持仓空头 + funding > 0 → 收入 funding（cash_delta > 0）
        """
        if not self.funding_cash_settlement_enabled:
            return 0.0
        if funding_time <= self.last_funding_time:
            return 0.0
        if not math.isfinite(funding_rate) or not math.isfinite(position_notional):
            return 0.0
        cash_delta = -funding_rate * position_notional
        self.funding_cash += cash_delta
        self.last_funding_rate = funding_rate
        self.last_funding_time = funding_time
        return cash_delta
```

**前向兼容**：所有新字段有默认值；老策略（不读这些字段）行为不变。

### 3.2 `FundingArbitrageConfig` 新增字段（`backend/strategy/core/strategy_config.py`）

```python
@dataclass
class FundingArbitrageConfig(StrategyConfig):
    # —— 已有（保留向后兼容）——
    # （注：原 config 字段保持不变，target_position 字段名延用）

    # —— 新增：触发参数 ——
    entry_threshold: float = 0.0003        # 入场阈值（0.03%）
    exit_threshold: float = 0.0001         # 退场阈值（0.01%）
    min_hold_bars: int = 8                 # 持续 N 根 bar 满足条件才触发（抗噪）

    # —— 新增：仓位参数 ——
    target_position_pct: float = 0.1       # 每腿目标 = equity × 10%
    spot_leg_enabled: bool = True          # 现货腿开关（False = 单边模式）
    spot_margin_enabled: bool = False      # 现货做空门控（默认保守关闭）

    # —— 新增：funding 结算 ——
    funding_interval_hours: int = 8        # funding 结算周期（binance 默认 8h）
    enable_funding_cash_settlement: bool = True

    # —— 新增：调试 ——
    log_state_transitions: bool = True     # 状态切换时打印到 ctx.log
```

**前向兼容**：所有新字段有默认值；老 `FundingArbitrageConfig()` 构造行为不变（退化为原版单边）。

### 3.3 `Action` 扩展（`backend/strategy/base.py`）

```python
@dataclass
class Action:
    # 现有字段
    target_position: float = 0.0          # 主腿（perp）目标仓位
    reason: str = ""
    metadata: dict = field(default_factory=dict)

    # 新增：现货腿目标仓位
    spot_target_position: float = 0.0
```

**前向兼容**：老策略（不写 `spot_target_position`）默认 0，行为不变。

### 3.4 `FundingArbitrage` 升级（`backend/strategy/templates/funding_arbitrage.py`）

#### 3.4.1 状态枚举

```python
from enum import Enum

class FundingState(Enum):
    FLAT = "flat"
    LONG_FUNDING = "long_funding"      # perp=short, spot=long
    SHORT_FUNDING = "short_funding"    # perp=long, spot=short（需 spot_margin）
```

#### 3.4.2 状态机

```python
class FundingArbitrage(BaseStrategy):
    def __init__(self, config: FundingArbitrageConfig | None = None):
        super().__init__(config or FundingArbitrageConfig())
        self._state: FundingState = FundingState.FLAT
        self._hold_counter: int = 0    # 持续时间计数器（抗噪）

    def on_bar(self, bar, ctx: StrategyContext) -> Action:
        # 1) settle funding（先于状态判断）
        position_notional = abs(ctx.position) * bar["close"]
        ctx.settle_funding(
            funding_rate=bar.get("funding_rate", 0.0),
            funding_time=bar.get("funding_time", bar.get("timestamp", 0)),
            position_notional=position_notional,
        )

        # 2) 状态机更新
        funding = bar.get("funding_rate", 0.0)
        prev_state = self._state
        new_state, perp_target, spot_target = self._next_state(funding)
        if new_state != prev_state and self.config.log_state_transitions:
            ctx.log(f"state: {prev_state.value} -> {new_state.value} (funding={funding:.6f})")
        self._state = new_state

        # 3) 输出 Action
        return Action(
            target_position=perp_target,
            spot_target_position=spot_target,
            reason=f"state={new_state.value} funding={funding:.6f}",
            metadata={
                "funding_cash": ctx.funding_cash,
                "last_funding_rate": ctx.last_funding_rate,
            },
        )

    def _next_state(self, funding: float) -> tuple[FundingState, float, float]:
        equity = self._get_equity()
        notional = equity * self.config.target_position_pct
        eps = 1e-9

        # 优先检查强反转（已持仓）
        if self._state == FundingState.LONG_FUNDING:
            if funding <= -self.config.entry_threshold:
                self._hold_counter += 1
                if self._hold_counter >= self.config.min_hold_bars:
                    return self._targets_for(SHORT_FUNDING, notional)
            elif funding < self.config.exit_threshold:
                self._hold_counter = 0
                return FundingState.FLAT, 0.0, 0.0
            else:
                self._hold_counter = 0
                return self._targets_for(LONG_FUNDING, notional)

        if self._state == FundingState.SHORT_FUNDING:
            if funding >= +self.config.entry_threshold:
                self._hold_counter += 1
                if self._hold_counter >= self.config.min_hold_bars:
                    return self._targets_for(LONG_FUNDING, notional)
            elif funding > -self.config.exit_threshold:
                self._hold_counter = 0
                return FundingState.FLAT, 0.0, 0.0
            else:
                self._hold_counter = 0
                return self._targets_for(SHORT_FUNDING, notional)

        # FLAT 状态判断入场
        if funding >= +self.config.entry_threshold:
            self._hold_counter += 1
            if self._hold_counter >= self.config.min_hold_bars:
                return self._targets_for(LONG_FUNDING, notional)
        elif funding <= -self.config.entry_threshold:
            self._hold_counter += 1
            if self._hold_counter >= self.config.min_hold_bars:
                return self._targets_for(SHORT_FUNDING, notional)
        else:
            self._hold_counter = 0
        return FundingState.FLAT, 0.0, 0.0

    def _targets_for(self, state: FundingState, notional: float) -> tuple[FundingState, float, float]:
        """根据状态计算双腿目标仓位。处理 spot 门控。"""
        if state == FundingState.FLAT:
            return state, 0.0, 0.0
        if state == FundingState.LONG_FUNDING:
            perp_target = -notional if self.config.spot_leg_enabled else -notional
            spot_target = +notional if self.config.spot_leg_enabled else 0.0
            return state, perp_target, spot_target
        if state == FundingState.SHORT_FUNDING:
            # 现货做空需要 margin
            spot_target = -notional if (self.config.spot_leg_enabled and self.config.spot_margin_enabled) else 0.0
            perp_target = +notional
            return state, perp_target, spot_target
        return state, 0.0, 0.0
```

#### 3.4.3 状态转换表

| 当前状态 | 触发条件 | 下一状态 | Perp 腿 | Spot 腿 |
|---|---|---|---|---|
| FLAT | funding ≥ +entry_threshold 持续 N bar | LONG_FUNDING | short +notional | long +notional |
| FLAT | funding ≤ -entry_threshold 持续 N bar | SHORT_FUNDING | long +notional | short +notional |
| LONG_FUNDING | funding < +exit_threshold | FLAT | 0 | 0 |
| LONG_FUNDING | funding ≤ -entry_threshold 持续 N bar | 反转 SHORT_FUNDING | 调仓 long | 调仓 short（需 margin）|
| SHORT_FUNDING | funding > -exit_threshold | FLAT | 0 | 0 |
| SHORT_FUNDING | funding ≥ +entry_threshold 持续 N bar | 反转 LONG_FUNDING | 调仓 short | 调仓 long |
| LONG_FUNDING | funding 在 [exit_threshold, entry_threshold] | 维持 | 0 变化 | 0 变化 |
| SHORT_FUNDING | funding 在 [-entry_threshold, -exit_threshold] | 维持 | 0 变化 | 0 变化 |

### 3.5 `baseline.py` 改造（`backend/backtest/baseline.py`）

#### 3.5.1 配置扩展

```python
@dataclass
class BacktestConfig:
    # ... 现有字段 ...
    funding_history_path: Optional[str] = None  # CSV: funding_time_ms,funding_rate
    spot_symbol: Optional[str] = None           # 双腿策略需要指定现货 symbol
```

#### 3.5.2 funding 历史加载

```python
def _load_funding_history(path: str) -> dict[int, float]:
    """返回 {funding_time_ms: funding_rate} 字典。"""
    history: dict[int, float] = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = int(row["funding_time_ms"])
            rate = float(row["funding_rate"])
            history[ts] = rate
    return history
```

#### 3.5.3 spot bar 索引

```python
def _build_spot_index(spot_bars: list) -> dict[int, object]:
    """spot bar 按 ts 索引。"""
    return {bar.ts: bar for bar in spot_bars}
```

#### 3.5.4 每 bar 注入

```python
# baseline.py 现有 line 149 附近改造
funding_history = (
    _load_funding_history(self.config.funding_history_path)
    if self.config.funding_history_path else {}
)
spot_index = (
    _build_spot_index(self._spot_bars)
    if self._spot_bars else {}
)

for bar in perp_bars:
    # ... 现有逻辑 ...
    bar_dict = bar.to_dict()
    bar_dict.setdefault("funding_rate", 0.0)
    bar_dict.setdefault("funding_time", bar.ts)  # 新增

    # 新增：查 funding 历史
    if funding_history:
        fr = funding_history.get(bar.ts)
        if fr is not None:
            bar_dict["funding_rate"] = fr
            bar_dict["funding_time"] = bar.ts

    # 新增：注入 spot close
    spot_bar = spot_index.get(bar.ts)
    if spot_bar is not None:
        ctx.spot_close = spot_bar.close
        ctx.spot_volume = spot_bar.volume
        ctx.spot_symbol = self.config.spot_symbol or ""

    strategy.on_bar(bar_dict, ctx)
```

#### 3.5.5 funding_cash 累加入账

```python
# baseline.py on_bar 调用之后（end of bar loop body）
# 已有 ledger 累加
ledger.add(ctx.funding_cash - ctx_prev_funding_cash, tag="funding_cash")
ctx_prev_funding_cash = ctx.funding_cash
```

### 3.6 Funding 历史 CSV 格式

```csv
funding_time_ms,funding_rate
1701302400000,0.000100
1701316800000,0.000300
1701331200000,0.000500
1701345600000,0.000400
1701360000000,0.000200
1701374400000,0.000050
1701388800000,0.000030
```

- **生产**：`binance public api /fapi/v1/fundingRate` 历史拉取生成
- **测试 fixture**：`tests/fixtures/funding_history_btcusdt_sample.csv`（24 条 8h 间隔，3 天）
- **缺失处理**：`bar_dict.funding_rate = 0.0` 静默回退（不报错）

### 3.7 自检脚本（`scripts/check_funding_arb.py`）

```python
"""Funding arbitrage 端到端自检。"""
import argparse
import asyncio
from pathlib import Path

from axon_quant import BacktestEngine
from strategy.templates.funding_arbitrage import FundingArbitrage
from strategy.core.strategy_config import FundingArbitrageConfig
from strategy.core.strategy_context import StrategyContext
from backtest.baseline import BaselineRunner, BacktestConfig

async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--perp-symbol", default="BTCUSDT-PERP")
    p.add_argument("--spot-symbol", default="BTCUSDT")
    p.add_argument("--start", default="2024-12-01")
    p.add_argument("--end", default="2024-12-08")
    p.add_argument("--funding-csv", required=True)
    args = p.parse_args()

    config = BacktestConfig(
        perp_symbol=args.perp_symbol,
        spot_symbol=args.spot_symbol,
        funding_history_path=args.funding_csv,
        start=args.start,
        end=args.end,
    )
    strategy = FundingArbitrage(FundingArbitrageConfig())
    ctx = StrategyContext(spot_symbol=args.spot_symbol)
    runner = BaselineRunner(config)
    result = await runner.run(strategy, ctx)

    # 断言
    assert result.final_equity > 0, "净值必须 > 0"
    assert ctx.funding_cash > 0, f"funding_cash 必须 > 0（正 funding 期），实际 {ctx.funding_cash}"
    assert strategy._state in (
        FundingState.FLAT,
        FundingState.LONG_FUNDING,
    ), f"7 天 BTCUSDT 应至少进 LONG_FUNDING，实际 {strategy._state}"
    delta = abs(result.perp_position + result.spot_position)
    assert delta < 1e-6, f"双腿 delta 必须 < 1e-6，实际 {delta}"
    print(f"✓ check_funding_arb passed: equity={result.final_equity:.2f}, funding_cash={ctx.funding_cash:.2f}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 4. 错误处理

| 错误情形 | 处理策略 | 实现位置 |
|---|---|---|
| `ctx.funding_cash` 溢出（极端大数） | `math.isfinite()` 检查 + 跳过累加 | `settle_funding()` |
| 现货 bar 缺失（spot_index miss）| `ctx.spot_close = 0.0` → 状态机跳过 spot 仓位变动（退化为单边） | baseline.py |
| funding 出现 NaN/Inf | `if not math.isfinite(funding_rate): return 0` | `settle_funding()` |
| 现货做空但 `spot_margin_enabled=False` | `spot_target=0, perp_target=原值`（自动降级） | `_targets_for()` |
| `entry_threshold < exit_threshold` | 启动时日志告警（不阻止运行） | `__init__` |
| funding CSV 时间戳对不上 | `bar_dict.funding_rate = 0.0` 静默回退 | baseline.py |
| 资金不足（净值 < 2 × notional）| 状态机照常输出 Action；baseline 可选"按比例缩"（本任务**不做**） | 后续 sprint |

---

## 5. 测试策略

### 5.1 单元测试（`tests/unit/strategy/test_advanced_templates.py`）

**保留 3 个**老测试（向后兼容）：

```python
def test_funding_arb_positive_rate_sells()
def test_funding_arb_negative_rate_buys()
def test_funding_arb_zero_rate_holds()
```

**新增 7 个**测试（覆盖新设计）：

```python
def test_funding_arb_enters_long_funding_after_min_hold_bars()
    # FLAT → funding 持续 9 bar > 0.0003 → LONG_FUNDING
    # 断言：state=LONG_FUNDING, perp_target<0, spot_target>0

def test_funding_arb_exits_on_threshold_drop()
    # LONG_FUNDING → funding 跌破 0.0001 → FLAT
    # 断言：state=FLAT, perp_target=0, spot_target=0

def test_funding_arb_reverses_to_short_funding()
    # LONG_FUNDING → funding ≤ -entry_threshold 持续 N bar → SHORT_FUNDING
    # 断言：state=SHORT_FUNDING, perp_target>0, spot_target<0 (spot_margin=True)

def test_funding_arb_resets_hold_counter_on_noise()
    # 8 bar funding > entry + 1 bar funding 噪声 + 1 bar funding > entry
    # 断言：counter 应被重置，未触发入场

def test_funding_arb_spot_leg_disabled_is_single_leg()
    # spot_leg_enabled=False, funding 触发 LONG_FUNDING
    # 断言：perp_target<0, spot_target=0

def test_funding_arb_spot_margin_disabled_downgrades_short_side()
    # spot_margin_enabled=False, funding < -entry 触发 SHORT_FUNDING
    # 断言：perp_target>0, spot_target=0（自动降级）

def test_funding_arb_accumulates_funding_cash_correctly()
    # 3 个 funding 时刻：0.0001, 0.0003, 0.0005，position=1 BTC
    # 期望：funding_cash = -(0.0001+0.0003+0.0005) × 50000 = -45 USD
    # 断言：abs(ctx.funding_cash - (-45)) < 0.01
```

### 5.2 集成测试（`tests/integration/test_funding_arb_backtest.py` 新建）

```python
def test_full_backtest_with_funding_csv_runs_to_completion()
    # baseline 跑 7 天 BTCUSDT + funding CSV → 无异常退出
    # 断言：result.status == "completed"

def test_backtest_equity_curve_includes_funding_cash()
    # 跑 30 天，end_equity - start_cash ≈ sum(funding_cash) + sum(price_pnl)
    # 断言：funding_cash 占比 > 0（确认 funding 真的被计入）

def test_backtest_with_missing_spot_data_degrades_gracefully()
    # 不提供 spot bar → funding 套利退化为单边
    # 断言：状态机仍正常运行，spot_target=0
```

### 5.3 自检脚本（`scripts/check_funding_arb.py`）

**断言**：
- 运行 7 天不崩
- `ctx.funding_cash > 0`（正 funding 期应累计正 cash）
- 状态机至少进入 LONG_FUNDING 一次
- 双腿仓位 delta < 1e-6

### 5.4 完整回测报告（`data/source/backtest_baselines/funding_arbitrage_BTCUSDT_2024-07_2025-07.{json,md}`）

格式沿用 P1-Sprint 2 基线报告标准：

```json
{
  "template": "funding_arbitrage",
  "symbol": "BTCUSDT",
  "period": "2024-07-01~2025-07-01",
  "total_pnl": ...,
  "funding_cash": ...,
  "sharpe_ratio": ...,
  "max_drawdown": ...,
  "win_rate": ...,
  "total_trades": ...,
  "report_path": "data/source/backtest_baselines/funding_arbitrage_BTCUSDT_2024-07_2025-07.md"
}
```

---

## 6. 范围与限制

### 6.1 前向兼容性（强保证）

- **3 个老单元测试**全部不破坏
- `FundingArbitrage()` 无参构造 = 退化为原单边版（`spot_leg_enabled=False` 等价行为）
- `StrategyContext` 新字段全部有默认值，老策略（不读新字段）行为完全不变
- `Action` 新字段 `spot_target_position` 默认 0，老策略输出 Action 不会因为 baseline 多读字段而出错（baseline 用 `getattr(action, 'spot_target_position', 0.0)` 防御）

### 6.2 安全约束

- **spot_margin_enabled 默认 False**：现货做空需要 margin 借贷，配置默认关闭避免账户被强平
- **funding 数值校验**：`settle_funding()` 用 `math.isfinite()` 防御 NaN/Inf
- **状态机纯内存**：不写 SQL，passive 重启可接受（重启从 FLAT 开始，符合"渐进建仓"原则）

### 6.3 性能约束

- 每 bar 增量 O(1)：settle_funding 一次 + 状态机 1 次判断 + Action 1 次构造
- 状态机逻辑：3 个 if-else 分支，无循环
- 不引入任何 Rust 调用（axon_quant 完全不调用 funding 相关 API）

### 6.4 数据约束

- **不新建 SQL 表**（项目约束）
- **不改 axon_quant 源码**（项目硬约束）
- **不动 P0-Sprint 已交付**：axon_bridge 适配层、12 子命令、7 种归档数据流

---

## 7. 风险登记

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| 现货做空需要 margin，配置打开后账户被强平 | **高** | 默认 `spot_margin_enabled=False`；spec 文档加红色警告；CHANGELOG 强调 |
| backtest 用 funding CSV 与真实 funding 不同步 | 中 | baseline 静默回退到 0 + 启动时日志告警 |
| 真实 funding 8h 一变，状态机在 1m bar 上频繁触发 hold_counter 累加噪声 | 中 | `min_hold_bars=8`（默认 8 根 1m bar = 8 分钟）足够抗短时噪声 |
| `ctx.funding_cash` 在 paper trading 与 backtest 公式可能不一致 | 中 | 公式统一写在 `settle_funding()`，所有调用方必须用它（不直接 +=） |
| 资金不足（净值 < 2 × notional）状态机仍输出目标 | 中 | 本任务**不做**按比例缩；记录到 CHANGELOG，下一 sprint 解决 |
| 老用户升级后行为漂移（funding 反转时不再立刻开仓）| 低 | CHANGELOG 写明；保留 `spot_leg_enabled=False` 即可退回单边版 |
| funding CSV 文件丢失导致 baseline 启动失败 | 低 | baseline 启动时 `if not path.exists(): warn + continue` |
| binance funding rate 历史 API 限流 | 低 | 自检脚本使用测试 fixture；生产环境用 binance client 缓存 |

### 7.1 风险缓解责任人

| 风险 | Owner | Review |
|---|---|---|
| 现货做空 margin 强平 | 用户（确认账户开通 margin） | spec review |
| funding CSV 同步 | baseline.py 维护者 | unit test |
| 老用户行为漂移 | CHANGELOG_funding_arb.md | spec review |

---

## 8. 回退方案

如果实盘发现设计有问题，按以下顺序回退（**不破坏现有功能**）：

### 8.1 配置级回退（最快）

```python
FundingArbitrageConfig(
    spot_leg_enabled=False,        # 退化为单边
    enable_funding_cash_settlement=False,  # 关闭 funding cash
)
```

老用户无感，行为等价于原版单边 FundingArbitrage。

### 8.2 代码级回退

把 `FundingArbitrage` 的 `__init__` 改为：

```python
def __init__(self, config=None):
    super().__init__(config or FundingArbitrageConfig())
    # 临时禁用状态机
    if os.environ.get("FUNDING_ARB_LEGACY") == "1":
        self._state = FundingState.FLAT
        self._hold_counter = 999  # 永不触发
```

环境变量开关，老代码可保留。

### 8.3 Git revert

本任务产出**单一 commit**（或 2-3 个小组 commit），可单独 revert。

### 8.4 模板注册回滚

从 `templates/__init__.py` 移除新版本，回滚到老 FundingArbitrage（v1 单边版）。

---

## 9. 交付物清单

| 文件 | 改动 | 验收 |
|---|---|---|
| `backend/strategy/core/strategy_context.py` | 改：+funding_cash, +spot_close, +spot_symbol, +settle_funding() | 单元测试 |
| `backend/strategy/core/strategy_config.py` | 改：+FundingArbitrageConfig 新字段 | 单元测试 |
| `backend/strategy/base.py` | 改：Action +spot_target_position | 单元测试 |
| `backend/strategy/templates/funding_arbitrage.py` | 改：升级为真双边 | 7 个新测试 |
| `backend/backtest/baseline.py` | 改：+funding_history_path, +spot_symbol, +每 bar 注入 | 3 个集成测试 |
| `tests/unit/strategy/test_advanced_templates.py` | 改：+7 个新测试 | pytest 通过 |
| `tests/integration/test_funding_arb_backtest.py` | 新建 | 3 个集成测试通过 |
| `tests/fixtures/funding_history_btcusdt_sample.csv` | 新建（24 行 8h 间隔）| 自检通过 |
| `scripts/check_funding_arb.py` | 新建 | end-to-end 通过 |
| `data/source/backtest_baselines/funding_arbitrage_BTCUSDT_2024-07_2025-07.{json,md}` | 新建 | 报告存在 |
| `docs/superpowers/specs/2026-07-17-funding-arbitrage-upgrade-design.md` | 新建（本文档）| 用户审 |
| `docs/superpowers/plans/2026-07-17-funding-arbitrage-upgrade.md` | 新建 | writing-plans skill |
| `docs/superpowers/CHANGELOG_funding_arb.md` | 新建 | 含本次变更清单 |

---

## 10. Open Questions（请用户审阅时确认）

| # | 问题 | 默认选择 |
|---|---|---|
| Q1 | 是否需要写 P2 路线（前端 UI 展示 funding 套利状态）| 否，本任务仅 CLI |
| Q2 | 是否需要多 symbol 同时 funding 套利（组合 funding）| 否，单 symbol |
| Q3 | `target_position_pct` 默认 0.1 是否合适 | 合理（10% 资金，保守起步）|
| Q4 | `min_hold_bars` 默认 8 是否合理（8 根 1m bar = 8 分钟）| 合理，足够抗噪 |
| Q5 | `entry_threshold=0.0003` (0.03%) 是否合理 | 合理（高于 0.01% 噪声）|
| Q6 | `funding_interval_hours=8` 是否要支持 4h/1h 自适应 | 否，统一 8h（binance 多数币对） |
| Q7 | 是否要在 spec 阶段就写 funding rate 历史 API 拉取脚本 | 否，下一 sprint |

---

## 11. 决策追溯（Brainstorming 摘要）

| 决策点 | 选项 | 选定 |
|---|---|---|
| 范围 | A 改造现有 / B 新建独立策略 / C 套 axon_quant 高级 API | **A** 改造现有 |
| 现货腿 | A 真双边 / B 合约单边 + 风险引擎对冲 / C 单边套个套利标签 | **A** 真双边 |
| funding 现金流 | A 策略层维护 / B 改 axon_quant / C 不在 backtest 结算 | **A** 策略层维护 |
| 触发逻辑 | A 阈值+持续时间 / B 滚动分位数 / C 信号反转 | **A** 阈值+持续时间 |

---

**End of Design — Awaiting User Review**
