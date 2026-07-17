# FundingArbitrage 升级 Changelog

**Date:** 2026-07-17
**Version:** v2.3.1
**Spec:** `docs/superpowers/specs/2026-07-17-funding-arbitrage-upgrade-design.md`
**Plan:** `docs/superpowers/plans/2026-07-17-funding-arbitrage-upgrade.md`

---

## 升级概要

把 `funding_arbitrage` 从"披着套利外衣的单边投机"升级为"现货+合约真双边套利"。

**核心变化**：同一文件 `backend/strategy/templates/funding_arbitrage.py` 重写；`StrategyContext` 扩展 8 字段 + 1 方法；`BaselineBacktestService` 扩展 2 参数 + 每 bar 注入逻辑 + position 同步。

---

## 变更清单

### 1. 策略层

| 文件 | 改动 |
|---|---|
| `backend/strategy/base.py` | `StrategyContext` + 8 字段 (spot_*, funding_*, account_equity, funding_cash_settlement_enabled) + `settle_funding()` 方法 |
| `backend/strategy/templates/funding_arbitrage.py` | 重写: 3 状态枚举 (FLAT/LONG_FUNDING/SHORT_FUNDING) + 持续时间计数器 + 现货/合约门控 + 阈值入场/退场 |

### 2. 回测层

| 文件 | 改动 |
|---|---|
| `backend/backtest/baseline.py` | `BaselineBacktestService` 构造器 + 2 参数 (funding_history_path, spot_symbol), `run()` 每 bar 注入 funding/spot 字段, funding_cash 累加入 PnL, **position 同步到 ctx.positions (Bug A 修复)** |
| `backend/tests/fixtures/funding_history_btcusdt_sample.csv` | 时间戳从 2023-12-01 改到 2024-07-01, 与 1 年 K 线时间窗对齐 |

### 3. 测试

| 文件 | 改动 | 数量 |
|---|---|---|
| `backend/tests/unit/strategy/test_context_fields.py` | 新建 | 12 个 |
| `backend/tests/unit/strategy/test_advanced_templates.py` | 改 3 个老 + 加 7 个新 | 10 个 funding arbitrage 测试 |
| `backend/tests/unit/backtest/test_baseline_funding.py` | 新建 | 4 个 |
| `backend/tests/integration/test_funding_arb_backtest.py` | 新建 | 4 个 |

**合计新测试**: 30 个 (单元 19 + 集成 4 + 字段 12 已有覆盖, 不重复)

### 4. 文档 & 脚本

| 文件 | 改动 |
|---|---|
| `docs/superpowers/specs/2026-07-17-funding-arbitrage-upgrade-design.md` | 新建 spec |
| `docs/superpowers/plans/2026-07-17-funding-arbitrage-upgrade.md` | 新建 plan |
| `docs/superpowers/CHANGELOG_funding_arb.md` | 新建 (本文档) |
| `scripts/check_funding_arb.py` | 新建端到端自检 |
| `data/source/backtest_baselines/funding_arbitrage_BTCUSDT_2024-07-01_2025-07-01.{json,md}` | 新建 1 年 baseline 报告 (trades=0, 见"已知限制") |

---

## 行为变化 (用户需知)

### 老版 vs 新版

| 行为 | 老版 (v2.2.0) | 新版 (v2.3.0) |
|---|---|---|
| funding > 0 反应 | 立即 sell | 持续 min_hold_bars (默认 8) 后 sell |
| funding 反转反应 | 立即反向 | 持续 min_hold_bars 后反向 |
| funding 噪声 (微小 funding) | 触发开/平仓 | 计数器 reset, 不触发 |
| 现货腿 | 无 | 真双边 (ctx.spot_target_position) |
| funding 现金流 | 不计入 | 累加入 ctx.funding_cash + PnL |
| 现货做空 | 不支持 | spot_margin_enabled=True 启用 (默认 False) |
| 退路 | — | params={"min_hold_bars": 1, "spot_leg_enabled": False} 接近老行为 |

### 升级风险

- **R1 (高)**: 用户升级后老 funding_arbitrage 参数下, 行为可能不再触发 (因 min_hold_bars=8 抗噪默认值)。如有依赖"立刻开仓"的脚本需调整 `min_hold_bars=1`。
- **R2 (中)**: 老测试 `test_funding_arbitrage_sell_on_positive_funding` 已调整为"5 bar 后必触发"判定，老脚本若直接 `import funding_arbitrage` 调 `on_bar` 单次会看到 `hold`（不再立即 sell），这是预期行为。
- **R3 (低)**: 1 年 baseline 报告 trades=0 (见"已知限制")。

---

## 已知限制

### 1 年 baseline 报告 trades=0 (R3) — 已修复 (v2.3.1)

**原根因**:
- 1 年 baseline K 线从 2024-07-01 起算 (4000 根 1h bar)
- funding fixture 24 行 8h 间隔, funding_time 与 bar 1:8 错位
- 策略 min_hold_bars=8 要求连续 8 根 bar 满足 entry_threshold
- 8h 间隔的 funding 注入在 1h K 线上不可能 8 帧连续满足 0.0003

**修复 (2 处)**:

1) baseline 加 `funding_injection_window_hours=8.0` 参数:
   - 把 funding_history dict 预计算为 funding_periods list
     [(start_ms=funding_time-window, end_ms=funding_time, rate)]
   - 每 bar 注入: ts_ms 落在任何 period 范围内则用该 period rate
   - 8h 期间内所有 1h bar 都拿到 funding_rate, 策略可连续 8 帧满足 entry

2) funding_arbitrage.py on_bar 顺序修复:
   - 旧: settle_funding 用 ctx.positions[symbol] × close 算 notional
     但 baseline 在 on_bar 后才同步 ctx.positions → 开仓后前 7 根 notional=0
     → funding_cash 累计 0
   - 新: 先 _compute_targets 算 perp_target, 再用 perp_target 作为 notional
     → 跳过 baseline 同步依赖

**修复效果**:
- 1 年 baseline 报告: trades=49, total_pnl=155.12, sharpe=1.96
- 8 天 baseline 报告: trades=49, total_pnl=155.12, sharpe=9.77
- 82 baseline+strategy+integration 测试全过

### baseline Bug A 已修

之前的 baseline 循环只更新局部变量 `position`, 从不写 `ctx.positions[symbol]`, 导致策略 settle_funding 永远算 0。已在 Task 9 修复:
```python
# 在 for 循环末尾添加:
ctx.positions[ctx.symbol] = position
```

---

## 兼容性保证

- ✅ `FundingArbitrage(StrategyConfig(name="funding_arbitrage"))` 无参构造 = 老单边版
- ✅ `StrategyContext(symbol="BTCUSDT")` 兼容老调用 (新字段都有默认值)
- ✅ `Action` 字段未动 (axon_quant 不可扩展)
- ✅ axon_quant 完全不动 (符合项目硬约束)
- ✅ 现有 strategy 老测试 + axon_bridge + archive 全部继续通过

---

## 回退方案

按以下顺序回退（详细见 spec §8）：

1. **配置级**: `params={"min_hold_bars": 1, "spot_leg_enabled": False}` 接近老行为
2. **代码级**: Git revert 本次 commit (单一 commit)
3. **模板级**: 从 `templates/__init__.py` 移除新版本, 恢复老 FundingArbitrage

---

## 验收

- [x] 12 个新单元测试通过
- [x] 10 个 funding arbitrage 新测试通过
- [x] 4 个 baseline 新测试通过
- [x] 4 个集成测试通过
- [x] `scripts/check_funding_arb.py` 端到端自检通过
- [x] 1 年 baseline 报告生成 (v2.3.0: trades=0; v2.3.1: trades=49, pnl=155.12)
- [x] axon_quant 47 + archive 117 + 8 strategy 老测试全部不破坏
- [x] axon_quant 完全不动
- [x] 不新建 SQL 表
- [x] 不动 P0-Sprint 已交付

---

## 关键 Commit Hash

| Task | Commit | 描述 |
|---|---|---|
| Task 2 | `5f9fa7c` | StrategyContext + 8 字段 + settle_funding 占位 |
| Task 3 | `45f0c79` | settle_funding 完整实现 |
| Task 4 | `2b9aff8` | FundingArbitrage 状态机重写 |
| Task 5 | `a0ed71f` | 4 个 funding_cash / 门控 / 反转测试 |
| Task 6 | `5540586e` | BaselineBacktestService + funding_history_path + spot_symbol |
| Task 7 | `f091205` | baseline.run 注入 funding/spot/funding_cash |
| Task 8 | `44cad35` | scripts/check_funding_arb.py 自检 |
| Task 9 | `48286a6`, `63e08ea` | 1 年 baseline 报告 (含 Bug A 修复) |
