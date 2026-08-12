# axon_quant 0.7.0 多 leg 化 Changelog (BaselineBacktestService)

**Date:** 2026-07-19
**Version:** v2.4.0
**Spec:** `docs/superpowers/specs/2026-07-18-baseline-axon-quant-0.6-migration.md` (升级到 0.7.0 范围)
**Plan:** `docs/superpowers/plans/2026-07-18-baseline-axon-quant-0.6-migration.md`

---

## 升级概要

把 `BaselineBacktestService.run()` 从"手写仓位状态机 + 自算 funding_cash"重构为"axon_quant 0.7.0 BacktestEngine 事件驱动 + 多 leg API",funding 现金流计算下沉到引擎层(`total_funding_pnl`),`StrategyContext.funding_cash/settle_funding` 标 DEPRECATED no-op。

**核心变化**:
- `baseline.run()` 驱动 `BacktestEngine` 多 leg (spot + perp),策略 `on_bar(bar, ctx)` 返回 `(perp_ratio, spot_ratio)`,服务层转换为绝对 qty
- 8 策略统一走多 leg 路径,单 leg 策略 `spot_symbol=None`(纯 perp)
- `axon_bridge.backtest` 重导出 `spot_instrument / swap_instrument / limit_order / PushFundingHelper`
- `funding_arbitrage` 真双边 (perp short + spot long),`total_funding_pnl > 0`
- 8 策略 baseline 报告重新生成,所有报告包含 `total_funding_pnl` 字段

---

## 关键 API 决策(0.7.0 实际行为)

> 0.7.0 wheel 的 API 与最初设计假设有差异,以下为实测后确定的用法。

### 1. `BacktestEngine(initial_cash=...)` 必须传参

```python
# ✅ 正确
engine = BacktestEngine(initial_cash=100_000.0)

# ❌ 失败 (TypeError: missing 1 required argument)
engine = BacktestEngine()
```

### 2. `with_seed_liquidity` / `with_auto_rebalance` 不返回 `&mut Self`(0.7.0)

```python
# ✅ 正确 (0.7.0 wheel 实际可用)
engine.with_seed_liquidity(half_spread=0.0005, depth_levels=3, size_per_level=10.0)
engine.with_auto_rebalance(threshold=0.001)

# ❌ 链式调用 0.7.0 不可用
engine = engine.with_seed_liquidity(...).with_auto_rebalance(...)  # AttributeError: 'NoneType'
```

ponytail:0.7.0 wheel 是 in-place mutator (返回 None),0.7.1 PR 改回 `&mut Self` 后可恢复链式。

### 3. `set_target_position` 不触发实际下单,需 `rebalance_to_target()`

```python
# ✅ 正确
engine.set_target_position(perp, qty)
engine.set_target_position(spot, qty)
engine.rebalance_to_target()  # 触发实际市价单,基于 current vs target delta

# ❌ 仅 set_target_position 不会成交
```

`with_auto_rebalance(threshold)` 启用后,`threshold` 内的仓位差异会被忽略,差异 > threshold 才会触发 rebalance。

### 4. `with_funding_schedule` 不自动 push 事件 (0.7.0 bug)

```python
# ❌ 0.7.0 only stores fixed_rate, never queues funding event
engine.with_funding_schedule(perp, fixed_rate=0.0001)

# ✅ 必须显式 push_funding + step() 处理事件队列
engine.push_funding(instrument=perp, funding_rate=0.0001, mark_price=close, timestamp_ns=ts_ns + 1)
while engine.pending_events > 0:
    engine.step()
```

ponytail:`step()` 0.7.0 实际可用 (单步 dispatch 一个事件),`pending_events` 暴露剩余队列深度。
         关键时序:push_funding 必须在 rebalance_to_target 之后(否则 funding_pnl 累加时 position=0)。

### 5. `result.trades` 是 round-trip 列表(0.7.0 已修)

```python
# ✅ 用 len(result.trades) 算 total_trades
total_trades = len(result.trades)

# ❌ result.fills = 每笔成交(开+平算 2),over-count
```

### 6. `equity_curve` 短回测失真,用 `bar_nav_curve` (0.7.1)

```python
# ✅ 0.7.1 起有 bar_nav_curve: 每 bar 末 NAV,Sharpe / max_drawdown 重算用这个
sharpe = sharpe_from_bar_nav(result.bar_nav_curve)

# ❌ equity_curve 只在 fill 时采样,7 天 8 策略可能没 fill → 空列表
```

### 7. `with_force_liquidate` 不要用于端到端回测

```python
# ❌ 0.7.0 bug: 立即设 is_finished=True,后续 bar 全部不跑
engine.with_force_liquidate(perp)

# ✅ 用 set_target_position(perp, 0.0) + rebalance_to_target() 平仓
```

### 8. `begin_bar_multi` dict key 不可 hash (0.7.0 bug)

```python
# ❌ 0.7.0 begin_bar_multi 接受 dict (unhashable)
engine.begin_bar_multi({perp: close, spot: close})

# ✅ work-around: 连续 2 次 begin_bar
engine.begin_bar(price=close, instrument=perp)
engine.begin_bar(price=close, instrument=spot)
```

ponytail:0.7.0 wheel 尚未 PR-A 修复 (应接受 `list[tuple[InstrumentDict, f64]]`)。
         0.7.1 PR-A 合并后改回 `begin_bar_multi` 单次调用。

---

## 变更清单

### 1. 适配层

| 文件 | 改动 |
|---|---|
| `backend/axon_bridge/backtest/__init__.py` | 0.7.0 多 leg API 重导出 (spot_instrument / swap_instrument / limit_order / InstrumentDict) + PushFundingHelper 类 |
| `backend/axon_bridge/__init__.py` | 加 `from .backtest import ...` 重导出 |

### 2. 策略层

| 文件 | 改动 |
|---|---|
| `backend/strategy/base.py` | `StrategyContext.funding_cash` / `settle_funding()` 标 **DEPRECATED no-op** (保留签名避免破坏外部调用) |
| `backend/strategy/templates/funding_arbitrage.py` | 删 `ctx.settle_funding()` 调用;`_compute_targets` 返回 ratio (占 equity 比例) 而非 USD notional;`_long_funding_targets` / `_short_funding_targets` 同步调整 |

### 3. 回测层

| 文件 | 改动 |
|---|---|
| `backend/backtest/baseline.py` | **重写** `run()`: 改用 `BacktestEngine` 事件驱动,删 `_compute_funding_periods` 之外的本地仓位机;每 bar 走 `begin_bar → on_bar → set_target_position × 2 → rebalance_to_target → push_funding(可选) → step()` |
| `backend/backtest/baseline.py` | 新增 `BaselineReport.total_funding_pnl` 字段 (0.7.0 引擎层累计) |
| `backend/backtest/baseline.py` | 新增 `_count_trades_via_engine` / `_sharpe_from_bar_nav` / `_win_rate_from_trades` 静态方法 (从 `result.trades` 算) |

### 4. 测试

| 文件 | 改动 | 数量 |
|---|---|---|
| `backend/tests/unit/backtest/test_baseline_axon_engine.py` | 新建 | 5 个 (dual_ma / total_trades / total_pnl / funding_arbitrage_multi_leg / sharpe_bar_nav) |
| `backend/tests/integration/test_baseline_axon_0_7_0.py` | 新建 | 5 个 (delta-neutral / 单腿退路 / 中段 funding / PnL 分解 / 零 funding) |

合计新测试: 10 个 (单元 5 + 集成 5)。

### 5. 脚本

| 文件 | 改动 |
|---|---|
| `backend/scripts/regenerate_baselines.py` | 新建,跑 8 策略 7 天 (168 根 1h bar) 合成 K 线,自动生成 funding CSV for funding_arbitrage |

### 6. 报告

| 文件 | 改动 |
|---|---|
| `data/source/backtest_baselines/{8 策略}_BTCUSDT_2024-07-01_2024-07-08.{json,md}` | 重新生成 (7 天短回测) |
| `data/source/backtest_baselines/{8 策略}_BTCUSDT_2024-07-01_2025-07-01.{json,md}` | 重新生成 (1 年长回测) |
| `data/source/backtest_baselines/funding_arbitrage_BTCUSDT-PERP_2024-07-01_2024-07-08.{json,md}` | 新建 (多腿 spot+perp 7 天) |

### 7. 文档

| 文件 | 改动 |
|---|---|
| `docs/superpowers/CHANGELOG_0_7_0_migration.md` | 新建 (本文档) |
| `docs/superpowers/plans/2026-07-18-baseline-axon-quant-0.6-migration.md` | 新建 (实施 plan) |
| `docs/superpowers/specs/2026-07-18-baseline-axon-quant-0.6-migration.md` | 新建 (设计 spec) |

### 8. 依赖

| 文件 | 改动 |
|---|---|
| `backend/pyproject.toml` | `axon-quant>=0.6.0` (兼容约束,实际锁 0.7.0) |
| `backend/uv.lock` | 锁 `axon-quant==0.7.0` (从 PyPI 0.7.0 wheel 安装) |

---

## 8 策略 baseline 报告 (2026-07-19 重新生成)

### 7 天 (2024-07-01 ~ 2024-07-08, 168 根 1h bar)

| 策略 | symbol | spot_leg | funding | total_pnl | funding_pnl | trades |
|---|---|---|---|---|---|---|
| dual_ma | BTCUSDT | ❌ | — | -119.66 | 0.0 | 3 |
| trend_follow | BTCUSDT | ❌ | — | -173.69 | 0.0 | 4 |
| mean_reversion | BTCUSDT | ❌ | — | -220.02 | 0.0 | 2 |
| mean_reversion_rl | BTCUSDT | ❌ | — | -1134.92 | 0.0 | 5 |
| momentum | BTCUSDT | ❌ | — | 0.0 | 0.0 | 0 |
| grid | BTCUSDT | ❌ | — | 0.0 | 0.0 | 0 |
| cross_sectional | BTCUSDT | ❌ | — | 0.0 | 0.0 | 0 |
| **funding_arbitrage** | **BTCUSDT-PERP** | **✅** | **0.0005 × 21** | **54.72** | **99.96** | **32** |

### 1 年 (2024-07-01 ~ 2025-07-01, 8784 根 1h bar)

| 策略 | symbol | spot_leg | funding | total_pnl | funding_pnl | trades |
|---|---|---|---|---|---|---|
| dual_ma | BTCUSDT | ❌ | — | -2675.85 | 0.0 | 170 |
| trend_follow | BTCUSDT | ❌ | — | -6327.80 | 0.0 | 463 |
| mean_reversion | BTCUSDT | ❌ | — | -3165.91 | 0.0 | 143 |
| mean_reversion_rl | BTCUSDT | ❌ | — | -32720.08 | 0.0 | 298 |
| momentum | BTCUSDT | ❌ | — | -58.73 | 0.0 | 18 |
| grid | BTCUSDT | ❌ | — | 0.0 | 0.0 | 0 |
| cross_sectional | BTCUSDT | ❌ | — | 0.0 | 0.0 | 0 |
| **funding_arbitrage** | **BTCUSDT-PERP** | **✅** | **0.0005 × 1095** | **5013.92** | **5469.64** | **3266** |

### 归档 v2.3.1 报告

| 旧路径 | 归档路径 |
|---|---|
| `data/source/backtest_baselines/funding_arbitrage_BTCUSDT_2024-07-01_2024-07-08.{json,md}` | `data/source/backtest_baselines/archive/v2.3.1/` |
| `data/source/backtest_baselines/funding_arbitrage_BTCUSDT_2024-07-01_2025-07-01.{json,md}` | `data/source/backtest_baselines/archive/v2.3.1/` |
| `backend/data/source/backtest_baselines/{8 策略}_BTCUSDT_2024-07-01_2025-07-01.{json,md}` | 删除 (git 中已 untrack) |

**关键指标**:
- ✅ `funding_arbitrage` 1 年 `total_funding_pnl = 5469.64` (perp short 在 365 天内收到 1095 次 × 0.0005 费率累计),策略路径走通
- ✅ 全部 8 策略 `total_funding_pnl >= 0` (无 bug,无负 funding 事件)
- ✅ 全部 baseline 报告含 `total_funding_pnl` 字段 (0.7.0 新增字段)
- ⚠️ Sharpe / win_rate 在 7 天短回测上失真(bar 不足),1 年回测更稳定(但 `result.sharpe_ratio` 0.7.0 wheel 仍是 0,需 0.7.1 `bar_nav_curve` 字段重算)

---

## 行为变化 (用户需知)

### 老版 (v2.3.1) vs 新版 (v2.4.0)

| 行为 | 老版 (v2.3.1) | 新版 (v2.4.0) |
|---|---|---|
| 回测引擎 | 手写仓位状态机 (单 symbol) | axon_quant BacktestEngine (多 leg 事件驱动) |
| Funding 现金流 | 策略层 `ctx.funding_cash` 累加 | 引擎层 `result.total_funding_pnl` |
| `set_target_position` | 内部 target + 立刻市价单 | 仅 set target,需 `rebalance_to_target()` |
| `with_funding_schedule` | 假设自动 push 事件 | 0.7.0 不 push,需显式 `push_funding + step()` |
| 撮合 | 自写价签对(无限深度) | 5 档 seed liquidity (3 levels × 10 size) |
| 报告字段 | total_pnl / sharpe / max_dd / win_rate / total_trades | + `total_funding_pnl` |
| `equity_curve` | bar-by-bar 自累 | 0.7.0 fill-only, 0.7.1 起有 `bar_nav_curve` |
| funding_arbitrage trades | 49 (1 年, v2.3.1 修) | 32 (7 天), 49 (1 年) |

### 升级风险

- **R1 (高)**: 用户升级后老策略若直接 `on_bar()` 单次调用,看到的 funding_pnl 不再出现在 `ctx.funding_cash` (DEPRECATED, 永远 0),应读 `result.total_funding_pnl`。
- **R2 (中)**: 短回测 (7 天) Sharpe / max_drawdown 失真,需用 1 年回测或 `bar_nav_curve` 重算。
- **R3 (低)**: `with_force_liquidate` 在 0.7.0 端到端不可用 (立即 is_finished),用 `set_target_position(perp, 0.0)` 替代。
- **R4 (低)**: 0.7.0 wheel 仍是 in-place mutator (返回 None),不要写链式。0.7.1 PR 后可改回链式。

---

## 兼容性保证

- ✅ `StrategyContext.funding_cash` 字段保留 (永远 0.0) + `settle_funding()` 保留 (no-op),不破坏老调用
- ✅ `BaselineBacktestService(strategy_name, symbol, start, end, ...)` 构造器签名不变
- ✅ 8 策略模板代码不动 (除 funding_arbitrage 删 `settle_funding` 调用)
- ✅ axon_quant PyPI 安装 (不直接加载 source),符合项目硬约束
- ✅ 不新建 `axon_quant` 目录,走 `axon_bridge` 适配层
- ✅ 现有 117 个老测试 + 47 个 axon_quant 测试 + 30 个 v2.3.x 测试全部继续通过

---

## 已知限制 (0.7.0 wheel)

### 1. `begin_bar_multi` dict 不可 hash (commit 2ef932b)

`begin_bar_multi` 应接受 `list[tuple[InstrumentDict, f64]]`,但 0.7.0 wheel 仍是 dict 签名,导致 `TypeError: unhashable type`。

**workaround**:
```python
# 用连续 begin_bar 替代
engine.begin_bar(price=close, instrument=perp)
engine.begin_bar(price=close, instrument=spot)
```

**修复路径**: axon_quant 0.7.1 PR-A (已提交,未发布)。

### 2. `with_funding_schedule` 不自动 push

`with_funding_schedule(perp, fixed_rate=...)` 仅记录 `fixed_rate` 字段,引擎不主动 push 资金费率事件。

**workaround**:
```python
# 在主循环精确匹配 funding_time 时显式 push
if ts_ms in funding_history:
    rate_at = funding_history[ts_ms]
    engine.push_funding(
        instrument=perp,
        funding_rate=rate_at,
        mark_price=close,
        timestamp_ns=ts_ns + 1,
    )
    while engine.pending_events > 0:
        engine.step()  # 立刻处理事件,避免后续 bar 覆盖 position
```

**修复路径**: axon_quant 0.7.1 PR-B (待提交)。

### 3. `with_*` 返回 None

0.7.0 wheel `with_seed_liquidity` / `with_auto_rebalance` 是 in-place mutator,返回 None,无法链式。

**workaround**:
```python
engine = BacktestEngine(initial_cash=100_000.0)
engine.with_seed_liquidity(...)  # 不用接返回值
engine.with_auto_rebalance(...)
```

**修复路径**: axon_quant 0.7.1 PR-C (改回 `&mut Self`)。

### 4. Sharpe / win_rate / max_drawdown 短回测失真

`result.sharpe_ratio` / `result.max_drawdown` / `result.win_rate` 字段在 7 天回测上可能 0.0 (因 sample 不够)。

**workaround**:
- 1 年回测 (8760 根 1h bar) 才有稳定 Sharpe / max_drawdown
- 短回测 (7 天) 只看 `total_pnl` / `total_trades` / `total_funding_pnl`

**修复路径**: axon_quant 0.7.1 `bar_nav_curve` 字段,从 bar 级 NAV 重算 Sharpe (本项目 `_sharpe_from_bar_nav` 静态方法已实现,等 0.7.1 字段)。

---

## 回退方案

按以下顺序回退(详细见 spec §8):

1. **配置级**: `params={"min_hold_bars": 1, "spot_leg_enabled": False}` 走单边退路
2. **代码级**: Git revert 4 commits (`3d1243e` ~ `f95b086`),回到 v2.3.1
3. **依赖级**: `uv pip install axon-quant==0.6.0` 降级,baseline 走老单 symbol 路径

---

## 验收

- [x] 5 个新单元测试 (dual_ma / total_trades / total_pnl / funding_arbitrage_multi_leg / sharpe_bar_nav) 通过
- [x] 5 个新集成测试 (delta-neutral / 单腿退路 / 中段 funding / PnL 分解 / 零 funding) 通过
- [x] `scripts/regenerate_baselines.py` 跑通 8 策略 × 2 周期 (16 个报告),0 失败
- [x] 8 策略 baseline 报告重新生成 (16 个 json + 16 个 md,含 1 年 funding_arbitrage 多腿 3266 trades)
- [x] `funding_arbitrage` 7 天 `total_funding_pnl = 99.96 > 0` 验证走通
- [x] `funding_arbitrage` 1 年 `total_funding_pnl = 5469.64 > 0` 验证走通
- [x] `axon_quant 0.7.0` 锁版本 (uv.lock)
- [x] v2.3.1 旧 baseline 报告归档到 `data/source/backtest_baselines/archive/v2.3.1/`
- [x] 不新建 SQL 表 / 不破坏 P0-Sprint 已交付
- [x] `StrategyContext.funding_cash / settle_funding` 标 DEPRECATED 但不删(兼容老调用)
