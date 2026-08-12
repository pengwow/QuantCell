# axon_quant 0.7.1 适配 Changelog (BaselineBacktestService)

**Date:** 2026-07-19
**Version:** v2.4.1
**Based on:** [CHANGELOG_0_7_0_migration.md](./CHANGELOG_0_7_0_migration.md)
**Scope:** 适配 axon_quant 0.7.1 PyPI wheel 的三个 PR-A/B/C 修复

---

## 升级概要

axon_quant 0.7.1 修复了 0.7.0 的三个 P0 痛点 (PR-A/B/C),使 `BaselineBacktestService` 代码可读性显著提升,但**`total_funding_pnl` 累加仍未完全修复** — `with_funding_schedule` 触发的 funding event 仍因 mark 处理 bug 累计为 0,**继续沿用手动 `push_funding` + `step()` work-around**。

**核心变化 (相对于 0.7.0)**:
- ✅ `with_*` 方法全部 `&mut Self` chainable (PR-C)
- ✅ `begin_bar_multi(legs: list[tuple])` 接受 `list[tuple[InstrumentDict, f64]]` (PR-A)
- ✅ `result.bar_nav_curve` 字段可用,Sharpe / max_drawdown 重算无需本地维护 NAV
- ⚠️ `with_funding_schedule` (PR-B) 仍不累计 `total_funding_pnl`,需手动 `push_funding`

---

## 关键 API 决策 (0.7.1 实际行为)

> 以下用 Python introspection 实际验证 (2026-07-19, axon-quant 0.7.1 wheel)。

### 1. `with_*` 方法全部 chainable (PR-C 合并)

```python
# ✅ 正确 (0.7.1 PR-C)
engine = (
    BacktestEngine(initial_cash=100_000.0)
    .with_seed_liquidity(half_spread=0.0005, depth_levels=3, size_per_level=10.0)
    .with_auto_rebalance(threshold=0.001)
    .with_funding_schedule(
        instrument=perp,
        interval_ns=8*3600*1_000_000_000,
        fixed_rate=0.0005,
        mark_aware=True,
    )
)
```

实测 `with_seed_liquidity` / `with_auto_rebalance` / `with_force_liquidate` / `with_funding_schedule` / `with_funding_schedule_disable` / `with_auto_rebalance_disable` / `with_matching_engine` / `with_fee_config` / `with_seed_liquidity_for` 全部返回同一个 `BacktestEngine` 实例 (chainable)。

`0.7.0` 的 in-place 写法仍兼容 (返回 `None` 然后继续 None,实际无副作用,代码仍可工作):

```python
# 0.7.0 / 0.7.1 兼容写法 (但 0.7.0 返回 None 后会被覆盖)
engine = BacktestEngine(initial_cash=100_000.0)
engine.with_seed_liquidity(...)  # 0.7.0: None, 0.7.1: engine
engine.with_auto_rebalance(...)  # 0.7.0: None, 0.7.1: engine
```

ponytail: 0.7.1 链式是首选,旧版兼容写法可作 defensive 风格。

### 2. `begin_bar_multi(legs: list[tuple])` (PR-A 合并)

```python
# ✅ 正确 (0.7.1 PR-A)
engine.begin_bar_multi(legs=[(perp, close), (spot, close)])

# ❌ 0.7.0 旧 API: dict 形式不可 hash
engine.begin_bar_multi(legs={perp: close, spot: close})  # TypeError: unhashable type
```

`legs` 形参语义:`list[tuple[InstrumentDict, f64]]`,每项是 `(instrument_dict, price)`。

### 3. `bar_nav_curve` 字段 (新增)

```python
result = engine.run()
# bar_nav_curve: [(ts_ns, nav), ...] 每根 bar 末采样
sharpe = sharpe_from_bar_nav(result.bar_nav_curve)  # 推荐:每 bar 都有帧
# equity_curve: 仅 fill/mark/funding 时采样 → 短回测可能为空
sharpe = sharpe_from_equity_curve(result.equity_curve)  # 不推荐
```

`0.7.0` 短回测 (7d 168 bar) 跑无 fill 策略时 `equity_curve` 仅 1 帧 = `[initial_cash]`,Sharpe 算 0/0=NaN。`bar_nav_curve` 修复此问题。

### 4. `with_funding_schedule` 仍不累计 funding_pnl (PR-B 半完成)

```python
# ⚠️ 0.7.1 PR-B: auto-push 触发 (begin_bar 收尾遍历 schedule,
#    last_funding_ts + interval_ns <= bar_ts 时合成 FundingEvent 入队),
#    但 funding_pnl 仍 0.0 (实测)。
#
# 根因:funding event 在 begin_bar 收尾触发时,rebalance 之前 position=0,
#       handle_funding 读 position=0 → cash_delta=0 → 漏算。
#       mark_aware=True / False 都不影响此行为。
#
# ✅ 仍需手动 push_funding + step() (沿用 0.7.0 work-around)
if ts_ms in funding_history:
    engine.push_funding(
        instrument=perp,
        funding_rate=rate_at,
        mark_price=close,
        timestamp_ns=ts_ns + 1,  # +1ns 排在 rebalance fill event 之后
    )
    while engine.pending_events > 0:
        engine.step()  # drain,确保 funding 在持仓未平前结算
```

实测对比 (同一 setup,短 perp -1.0 @ 50000 mark):

| 方式 | total_funding_pnl | 说明 |
|------|-------------------|------|
| 手动 `push_funding` + `step()` | **25.0** | ✅ 正确 |
| `with_funding_schedule` (PR-B) | **0.0** | ❌ position 读取时序 bug |

ponytail: `with_funding_schedule` PR-B 在 0.7.1 只完成了 "auto-push 触发" 这一半;另一半 (dispatch 时机正确) 留给 0.7.2 / 0.8.0。期间 `BaselineBacktestService` 继续用手动 `push_funding` + `step()` 模式。

### 5. `set_target_position` 仍需 `rebalance_to_target()` (无变化)

```python
# ✅ 正确
engine.set_target_position(perp, perp_qty)
engine.set_target_position(spot, spot_qty)
engine.rebalance_to_target()
```

`set_target_position` 0.7.0 / 0.7.1 行为一致:仅记录 target,不主动下单。

---

## 重构点 (0.7.1)

### `baseline.py::BaselineBacktestService.run()`

**之前 (0.7.0)**: 链式调用不可用,逐行配置:
```python
engine = BacktestEngine(initial_cash=initial_cash)
engine.with_seed_liquidity(half_spread=..., depth_levels=..., size_per_level=...)
engine.with_auto_rebalance(threshold=...)
```

**之后 (0.7.1)**: 链式调用更简洁:
```python
engine = (
    BacktestEngine(initial_cash=initial_cash)
    .with_seed_liquidity(
        half_spread=self._SEED_HALF_SPREAD,
        depth_levels=self._SEED_DEPTH_LEVELS,
        size_per_level=self._SEED_SIZE_PER_LEVEL,
    )
    .with_auto_rebalance(threshold=self._AUTO_REBALANCE_THRESHOLD)
)
```

### `baseline.py::BaselineBacktestService.run()` 主循环

**之前 (0.7.0)**: 两次 `begin_bar`:
```python
engine.begin_bar(close, perp)
engine.begin_bar(close, spot)  # bar_id +1,但 funding schedule 也 +1
```

**之后 (0.7.1)**: 单次 `begin_bar_multi`:
```python
engine.begin_bar_multi(legs=[(perp, close), (spot, close)])  # bar_id +1,funding schedule +1 合并
```

ponytail: 单次 `begin_bar_multi` 让 funding schedule 在 `last_funding_ts + interval_ns <= bar_ts` 时只触发 1 次 (而非 2 次),避免 funding 重复累加。

### `baseline.py::_sharpe_from_bar_nav` (新)

**之前 (0.7.0)**: 本地维护 `bar_nav: list[float]`:
```python
bar_nav.append(result.final_nav)  # 累加
sharpe = self._sharpe_from_bar_nav(bar_nav)
```

**之后 (0.7.1)**: 直接读 `result.bar_nav_curve`:
```python
sharpe = self._sharpe_from_bar_nav(getattr(result, "bar_nav_curve", []))
```

减少状态管理代码,且 `bar_nav_curve` 是引擎层采样,无遗漏 bar。

---

## 关键文件

| 文件 | 变更 |
|------|------|
| `backend/backtest/baseline.py` | chainable with_*, begin_bar_multi list[tuple], bar_nav_curve |
| `backend/tests/unit/backtest/test_baseline_axon_engine.py` | 新增 5 个测试覆盖 0.7.0 API |
| `backend/tests/integration/test_baseline_axon_0_7_0.py` | 5 个集成测试覆盖 delta-neutral 不变量 |
| `backend/scripts/regenerate_baselines.py` | 解析项目根,支持 7d+1y 双周期 |
| `data/source/backtest_baselines/*.json` | 重新生成 16 个 baseline 报告 (8 策略 × 2 周期) |
| `backend/uv.lock` | 升级 axon-quant 0.7.0 → 0.7.1 |
| `docs/superpowers/CHANGELOG_0_7_1_migration.md` | 本文档 |

---

## 测试结果

### 单元测试 (5/5 通过)
```
tests/unit/backtest/test_baseline_axon_engine.py
  ✓ test_baseline_dual_ma_via_axon_engine
  ✓ test_baseline_total_trades_uses_result_trades
  ✓ test_baseline_total_pnl_uses_final_nav_minus_initial
  ✓ test_baseline_funding_arbitrage_multi_leg
  ✓ test_baseline_sharpe_uses_bar_nav_curve
```

### 集成测试 (5/5 通过)
```
tests/integration/test_baseline_axon_0_7_0.py
  ✓ test_funding_arbitrage_delta_neutral_invariant
  ✓ test_funding_arbitrage_spot_disabled_falls_back_to_single_leg
  ✓ test_funding_arbitrage_funding_csv_mid_backtest
  ✓ test_funding_arbitrage_pnl_breakdown_is_consistent
  ✓ test_funding_arbitrage_zero_funding_yields_zero_funding_pnl
```

### Baseline 报告 (16/16 生成成功)
```
7d (2024-07-01~2024-07-08, 168 bars) + 1y (2024-07-01~2025-07-01, 8784 bars)
× 8 策略 (dual_ma, trend_follow, mean_reversion, mean_reversion_rl,
       momentum, grid, cross_sectional, funding_arbitrage)
= 16 reports

funding_arbitrage 关键指标 (1y):
  total_pnl: 5013.9234
  total_funding_pnl: 5469.6404
  total_trades: 3266
  sharpe_ratio: 31.7633
```

---

## 后续工作 (留给 0.7.2 / 0.8.0)

1. **`with_funding_schedule` mark 处理 bug** (axon_quant 侧)
   - 当前:funding event 在 `begin_bar` 收尾触发,rebalance 之前 position=0
   - 建议:funding event 触发时机改到 `end_bar` (所有 leg rebalance 后),或是在 `handle_funding` 时等当前 bar 所有 order 结算完
2. **`with_funding_schedule_disable` 显式 disable** (已加,但 unit test 缺失)
3. **`bar_nav_curve` 缓存机制** (每次 rebalance 都重算,大回测可能慢)

---

## Lessons Learned

- **0.7.0 假设的"链式 with_* + auto-push funding + dict 形式 begin_bar_multi"在 0.7.1 全部实现**,除了 funding mark 时序仍有问题。
- **PR 拆解** (PR-A dict→tuple, PR-B funding auto-push, PR-C chainable) 是典型的小步快跑模式:每个 PR 修一个具体问题,可独立 backport。
- **`pending_events` + `step()` 手动 drain 模式** 仍是 0.7.1 期间 funding 累计的唯一可靠方案。
- **`bar_nav_curve` 引入** 是事件驱动回测向 "engine-first metric" 演进的标志:策略层不再维护私有 NAV,引擎层直接采样,降低重复状态风险。
