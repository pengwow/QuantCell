# Baseline 全面 axon_quant 0.6.0 多 leg 化 Implementation Spec

> **Date:** 2026-07-18
> **Author:** QuantCell team
> **Status:** Draft — pending user review
> **Related:**
> - `docs/superpowers/CHANGELOG_funding_arb.md` v2.3.1 (上游交付)
> - `docs/superpowers/specs/2026-07-17-funding-arbitrage-upgrade-design.md` (上一版)
> - `docs/superpowers/specs/2026-07-16-axon-quant-integration-blueprint.md` (axon_quant 整合蓝图)
> - `http://127.0.0.1:8000/axon_quant/zh/reference/multi-leg-backtest/` (0.6.0 multi-leg 官方文档)

---

## 1. 目标

把 `BaselineBacktestService` 全面重构走 `axon_quant 0.6.0` 多 leg API：

1. **8 策略统一走多 leg 路径** —— 创建 spot + perp 两个 instrument leg，单 leg 策略只 set spot target（perp 永远 0），双 leg 策略 (funding_arbitrage) 反向 target。
2. **funding cash 计算完全下沉到 axon_quant 引擎** —— 策略层 `ctx.settle_funding()` 删除，baseline 读 `RunResult.total_funding_pnl`。
3. **axon_bridge 适配层加 0.6.0 多 leg 重导出** —— 业务代码统一从 `axon_bridge` 导入 `spot_instrument` / `swap_instrument` / `limit_order`。
4. **axon_quant 升级到 0.6.0** —— 借助 `push_funding` / `set_target_position` / `push_mark` / `with_funding_schedule` / `with_auto_rebalance` 引擎层能力。

---

## 2. 背景与动机

### 2.1 现状 (v2.3.1)

- `axon_quant==0.4.0`，无多 leg 抽象
- `BaselineBacktestService` 自己遍历 K 线 + 模拟 PnL + 注入 funding_rate
- `StrategyContext.settle_funding()` 策略层累加 funding_cash（hack）
- `funding_arbitrage` 状态机驱动 settle_funding + spot_target_position 双输出

### 2.2 痛点

- **funding cash 算两遍**：策略层 + baseline 都涉及，P&L 容易漂移
- **delta-neutral 风险靠策略层约定**：没有引擎层硬约束
- **funding 注入逻辑散落在 baseline**：8h 周期 + window 注入 = 复杂的 baseline 代码
- **测试复杂**：trades=0 修复要改 funding_injection_window_hours 等多个参数

### 2.3 axon_quant 0.6.0 提供的新能力

| 能力 | 0.6.0 API | 解决的问题 |
|---|---|---|
| Instrument 抽象 | `spot_instrument(base, quote)` / `swap_instrument(base, quote, settle, contract_size)` | spot/perp 是 first-class 对象，不再用 symbol 字符串 |
| 多 leg target | `engine.set_target_position(instrument, target)` | 显式表达 spot/perp 各自目标 |
| 引擎层 funding 结算 | `engine.push_funding(perp, rate, mark, ts_ns)` + `RunResult.total_funding_pnl` | 策略层不再算 funding_cash |
| 自动 rebalance | `engine.with_auto_rebalance(threshold)` + `RunResult.rebalances_triggered` | target→position 转换由引擎做 |
| 自动 funding 调度 | `engine.with_funding_schedule(perp, interval_ns, fixed_rate, mark_aware=True)` | 8h funding 周期内置（仅固定 rate） |
| 跨 leg 风险约束 | `RiskEngine.check_leg_pair(portfolio, &LegPair)` (Rust only，Python 暂未绑定) | delta 中性硬约束（0.6.0+ binding 收口后可用） |

### 2.4 不在本次范围

- ❌ 跨 leg 风险约束 `check_leg_pair` —— Python 绑定 0.6.0 未暴露
- ❌ `Strategy::streaming` 改造 —— 跟 baseline 回测无关
- ❌ DeFi 模块（`axon_quant.defi`）—— 跟 quant 策略无关
- ❌ LLM agent 集成 —— 已存在 `llm` 子模块，未在 baseline 路径

---

## 3. 设计

### 3.1 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│              BaselineBacktestService (重写)                  │
│  - 接收 strategy_name / symbol / kline / funding_fixture     │
│  - 驱动 axon_quant 0.6.0 BacktestEngine 多 leg              │
│  - 把 RunResult 转为 BaselineReport                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│         axon_quant 0.6.0 BacktestEngine (多 leg)            │
│  - spot_instrument + swap_instrument 抽象                   │
│  - set_target_position(spot) / set_target_position(perp)    │
│  - push_funding(perp) → 引擎层累加 total_funding_pnl        │
│  - push_mark(spot) / push_mark(perp) → mark 缓存            │
│  - with_seed_liquidity / with_auto_rebalance → 自动撮合     │
│  - run() → RunResult { total_pnl, total_funding_pnl,        │
│                        positions, leg_targets, marks,        │
│                        rebalances_triggered, ... }          │
└─────────────────────────────────────────────────────────────┘
                     ▲
                     │ 适配
┌────────────────────┴────────────────────────────────────────┐
│       axon_bridge.backtest (新增 0.6.0 多 leg 适配层)       │
│  - 重导出 spot_instrument / swap_instrument / limit_order   │
│  - push_funding_helper 装饰：接受 funding_history dict      │
│    转换为 (timestamp_ns, rate) 序列调 engine.push_funding  │
└─────────────────────────────────────────────────────────────┘
                     ▲
                     │ 调用
┌────────────────────┴────────────────────────────────────────┐
│              8 策略模板 (on_bar 返回 Action)                 │
│  - 单 leg (7 策略):  返回 Action → baseline 映射为 spot    │
│  - 双 leg (funding_arbitrage): 返回 Action → baseline       │
│    映射为 spot + perp 反向 target                           │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 BaselineBacktestService.run() 重写

```python
def run(self) -> BaselineReport:
    """驱动 axon_quant 0.6.0 BacktestEngine 多 leg 回测。"""
    df = self._load_kline()
    if df is None or df.empty:
        raise ValueError(f"K 线数据为空: {self.symbol} {self.interval} {self.start}~{self.end}")

    base, quote = self._parse_symbol(self.symbol)
    spot = spot_instrument(base, quote)
    perp = swap_instrument(base, quote, settle="usd_margin", contract_size=1.0)

    engine = BacktestEngine(initial_cash=100_000.0)
    engine.with_seed_liquidity(half_spread=0.5, depth_levels=2, size_per_level=2.0)
    engine.with_auto_rebalance(1e-6)  # 0.6.0 Phase 1 自动 rebalance

    strategy_cls = StrategyLoader.get(self.strategy_name)
    config = StrategyConfig(name=self.strategy_name, symbol=self.symbol)
    strategy: BaseStrategy = strategy_cls(config)
    ctx = StrategyContext(symbol=self.symbol)
    strategy.on_start(ctx)

    funding_history = self._load_funding_history()
    funding_helper = PushFundingHelper(funding_history)  # 把 funding fixture 转 push_funding 序列

    for _, row in df.iterrows():
        ts_ns = self._row_timestamp_ns(row)
        close = float(row["close"])

        # 推 mark (供 funding 结算 / 未实现 PnL 估值)
        engine.push_mark(spot, close, ts_ns)
        engine.push_mark(perp, close, ts_ns)

        # 种虚拟对手盘 (spot + perp 各自独立 book)
        engine.begin_bar(close, spot)
        engine.begin_bar(close, perp)

        # 推 funding (8h 周期按 fixture)
        funding_helper.maybe_push(perp, close, ts_ns, engine)

        # 策略生成 Action
        bar = self._build_bar(row, ts_ns)
        ctx.account_equity = ...  # 策略层算 notional 用
        action = strategy.on_bar(bar, ctx)

        # Action 映射到 2 leg target
        spot_target, perp_target = self._map_action_to_legs(action, strategy, ctx)
        engine.set_target_position(spot, spot_target)
        engine.set_target_position(perp, perp_target)

    result = engine.run()
    return self._build_report(result)


def _map_action_to_legs(
    self, action: Action, strategy: BaseStrategy, ctx: StrategyContext
) -> tuple[float, float]:
    """Action → (spot_target, perp_target)。

    - 单 leg 策略: spot_target = action.target_position, perp_target = 0
    - funding_arbitrage: spot_target = ctx.spot_target_position,
                        perp_target = action.target_position
                        (策略层自己保证 spot + perp 反向)
    """
    if hasattr(ctx, "spot_target_position") and ctx.spot_target_position != 0.0:
        # 双 leg 策略 (funding_arbitrage) 已在 ctx.spot_target_position
        return ctx.spot_target_position, float(action.target_position)
    # 单 leg 策略：spot target = action.target_position
    return float(action.target_position), 0.0
```

### 3.3 axon_bridge.backtest 新模块

```python
# backend/axon_bridge/backtest.py
"""axon_quant 0.6.0 多 leg 回测适配层。

ponytail: 业务代码统一从 axon_bridge 导入多 leg 工厂函数,
         跟其他子模块风格一致
"""
from axon_quant.backtest import (  # noqa: F401
    spot_instrument,
    swap_instrument,
    limit_order,
    InstrumentDict,
)


class PushFundingHelper:
    """funding fixture → engine.push_funding 调度器。

    ponytail: funding fixture 是 dict[ts_ms, rate],
             engine.push_funding 接受 (instrument, rate, mark, ts_ns)
             转换 + 重复时间防御一次过
    """

    def __init__(self, funding_history: dict[int, float]):
        self.funding_history = funding_history
        self._last_pushed_ts_ms: int = -1

    def maybe_push(
        self, perp: InstrumentDict, mark: float, ts_ns: int, engine: BacktestEngine
    ) -> None:
        """ts_ms 落点在 funding fixture 某个 key 附近 8h 窗口 → 推 funding。

        ponytail: 用 funding_rate_injection_window 兼容策略状态机:
                 fixture 8h 周期, 任何 bar 落点在 [ts - 8h, ts] 都能拿到 rate
                 8h 整点由策略状态机 (funding_arbitrage min_hold_bars=8) 触发
        """
        ts_ms = ts_ns // 1_000_000
        window_ms = 8 * 3600 * 1000
        for funding_ts_ms, rate in self.funding_history.items():
            if funding_ts_ms - window_ms <= ts_ms <= funding_ts_ms:
                if funding_ts_ms > self._last_pushed_ts_ms:
                    engine.push_funding(perp, rate, mark, funding_ts_ms * 1_000_000)
                    self._last_pushed_ts_ms = funding_ts_ms
                return  # 只推最近的 funding 事件
```

### 3.4 StrategyContext 调整

```python
@dataclass
class StrategyContext:
    symbol: str
    closes: list[float] = field(default_factory=list)
    positions: dict[str, float] = field(default_factory=dict)
    orders: list[dict] = field(default_factory=list)

    # —— 现货腿支持 (funding_arbitrage 仍然用) ——
    spot_target_position: float = 0.0

    # —— 账户净值 (策略层算 notional 用) ——
    account_equity: float = 0.0

    # —— DEPRECATED 字段 (保留读接口避免破坏外部代码) ——
    #   funding cash 完全下沉到 axon_quant 引擎的 total_funding_pnl
    #   策略层不再调用 settle_funding()
    funding_cash: float = 0.0  # DEPRECATED: 读返回 0
    last_funding_rate: float = 0.0  # DEPRECATED
    last_funding_time: int = 0  # DEPRECATED
    funding_cash_settlement_enabled: bool = False  # DEPRECATED, 默认 False

    def settle_funding(self, *args, **kwargs) -> float:  # DEPRECATED
        """DEPRECATED: funding cash 已下沉到 axon_quant 引擎。
        保留作 no-op 接口以避免破坏外部调用,返回 0.0。
        """
        return 0.0
```

### 3.5 funding_arbitrage.py 调整

策略层删 `ctx.settle_funding()` 调用，状态机只控制 target_position：

```python
def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
    funding_rate = float(bar.get("funding_rate", 0.0))
    funding_time = int(bar.get("timestamp", bar.get("funding_time", 0)))
    close_price = float(bar["close"])

    # 1) 状态机更新 (仍然)
    prev_state = self._state
    perp_target, spot_target, new_state = self._compute_targets(funding_rate)
    if new_state != prev_state and self._param("log_state_transitions"):
        ctx.orders.append({
            "type": "log",
            "msg": f"state: {prev_state.value} -> {new_state.value} (funding={funding_rate:.6f})",
        })
    self._state = new_state
    self._current_side = {...}[new_state]

    # 2) 写 ctx.spot_target_position (baseline 仍然读)
    ctx.spot_target_position = spot_target

    # 3) 不再调 ctx.settle_funding() — funding cash 累加由 axon_quant 引擎做
    #    (RunResult.total_funding_pnl 反映 funding cash)
    return Action(
        action_type=self._action_type_for(new_state),
        confidence=0.6,
        target_position=perp_target,
        model_id=self.config.name,
        inference_time_us=0,
    )
```

### 3.6 BaselineReport 字段扩展

```python
@dataclass
class BaselineReport:
    template: str
    symbol: str
    period: str
    interval: str
    candle_type: str
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    # —— 新增 0.6.0 字段 ——
    funding_pnl: float = 0.0           # 引擎层 funding 累计 (从 RunResult.total_funding_pnl 读)
    rebalances: int = 0                # 引擎 rebalance 触发次数 (从 RunResult.rebalances_triggered 读)
    engine_version: str = "0.6.0"      # 标记来源, 区别 v2.3.1 自算 PnL
    report_id: str
    generated_at: str
```

### 3.7 axon_quant 升级

通过 `uv pip install --upgrade axon-quant` 装最新（不锁版本），但在文档中声明 0.6.0+ 是最低要求：

```markdown
# backend/README.md 或 docs/superpowers/CHANGELOG_funding_arb.md
## 依赖
- Python 3.14+
- axon-quant >= 0.6.0 (不锁版本, pip install --upgrade)
```

`uv.lock` 中 `axon-quant` 条目由 `uv` 自动更新（`uv pip install --upgrade axon-quant` 会刷新 lock）。

---

## 4. 文件变更清单

| 文件 | 改动 | 备注 |
|---|---|---|
| `backend/axon_bridge/__init__.py` | 加 `from .backtest import spot_instrument, swap_instrument, limit_order, PushFundingHelper` | |
| `backend/axon_bridge/backtest.py` | **新建** | 0.6.0 多 leg 工厂 + PushFundingHelper |
| `backend/backtest/baseline.py` | **重写** `run()` 走 BacktestEngine；删 `_compute_funding_periods` / `funding_injection_window_hours` / funding_periods 逻辑；扩展 `BaselineReport` 字段 | |
| `backend/strategy/base.py` | `StrategyContext.settle_funding` / `funding_cash` / `last_funding_rate` / `last_funding_time` / `funding_cash_settlement_enabled` 标 DEPRECATED；`settle_funding()` 改为 no-op | 保留字段避免破坏外部代码 |
| `backend/strategy/templates/funding_arbitrage.py` | 删 `ctx.settle_funding()` 调用 | 状态机只控制 target |
| `backend/strategy/templates/cross_sectional.py` | 不变（单 leg 策略） | |
| `backend/strategy/templates/mean_reversion_rl.py` | 不变 | |
| `backend/strategy/templates/{dual_ma,trend_follow,mean_reversion,grid,momentum}.py` | 不变 | |
| `backend/tests/unit/strategy/test_advanced_templates.py` | 删 `test_funding_arbitrage_accumulates_funding_cash_on_long_funding` (已下沉)；改 `test_funding_arbitrage_spot_margin_disabled_downgrades` 等不影响 | 7 → 6 个 funding arbitrage 测试 |
| `backend/tests/unit/backtest/test_baseline_funding.py` | 删 4 个老测试 (构造器 funding_injection_window_hours / _compute_funding_periods)；加 5 个新测试 (0.6.0 多 leg 路径) | 7 → 5 个 baseline_funding 测试 |
| `backend/tests/integration/test_funding_arb_backtest.py` | 改 `test_backtest_equity_curve_includes_funding_cash` → 读 `result.total_funding_pnl`；加 1 个新测试 (delta-neutral 不变量) | 4 → 4 个 integration 测试 |
| `data/source/backtest_baselines/funding_arbitrage_BTCUSDT_2024-07-01_2025-07-01.{json,md}` | 重新生成 (新增 funding_pnl / rebalances 字段) | |
| `data/source/backtest_baselines/{7 个其他策略}_BTCUSDT_2024-07-01_2024-07-08.{json,md}` | 重新生成 (baseline 走 0.6.0 后数字会变) | 作为回归对比基线 |
| `docs/superpowers/CHANGELOG_funding_arb.md` | v2.3.1 → v2.3.2，新增"axon_quant 0.6.0 升级"段 | |
| `docs/superpowers/specs/2026-07-18-baseline-axon-quant-0.6-migration.md` | **本文档** | |
| `docs/superpowers/plans/2026-07-18-baseline-axon-quant-0.6-migration.md` | **新建 plan** (writing-plans skill 输出) | |

**总计**: 5 改 + 4 新建 + 2 重生成

---

## 5. 测试策略

### 5.1 单元测试

#### `test_axon_bridge_backtest.py` (新)
- `test_spot_instrument_dict`：验证 `spot_instrument("BTC", "USDT")` 返回正确 dict
- `test_swap_instrument_dict`：验证 `swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)`
- `test_push_funding_helper_basic`：fixture 1 个 funding → 调 1 次 push_funding
- `test_push_funding_helper_window_injection`：ts_ms 落点在 [ts-8h, ts] 范围触发
- `test_push_funding_helper_no_double_push`：重复 ts_ms 不重复 push

#### `test_advanced_templates.py` (改)
- 删 `test_funding_arbitrage_accumulates_funding_cash_on_long_funding`（已下沉到引擎，引擎测试在 axon_quant 上游）
- 保留其余 9 个测试

#### `test_baseline_funding.py` (改)
- 删 3 个 funding_injection_window_hours 测试（参数已删）
- 删 1 个 _load_funding_history 测试（baseline 改为读 PushFundingHelper，逻辑外移）
- 加 3 个新测试：
  - `test_baseline_uses_axon_quant_backtest_engine`：验证 baseline.run() 走 BacktestEngine
  - `test_baseline_maps_action_to_legs`：验证 Action → (spot_target, perp_target) 映射
  - `test_baseline_funding_pnl_from_engine_result`：验证 baseline.total_pnl + funding_pnl 读自 RunResult

### 5.2 集成测试

#### `test_funding_arb_backtest.py` (改)
- 改 `test_backtest_equity_curve_includes_funding_cash`：从 baseline 内 funding_cash 累加改为读 `result.total_funding_pnl`
- 加 `test_funding_arb_backtest_delta_neutral_invariant`：funding_arbitrage 入场后 spot+perp target 互反（delta 中性）

### 5.3 端到端测试

`scripts/check_funding_arb.py` (改)：
- 跑 baseline 1 年 + 8 天
- 验证 result.total_funding_pnl > 0 (LONG_FUNDING 期间吃 funding)
- 验证 spot_target + perp_target ≈ 0 (delta 中性)
- 验证 8 策略 baseline 报告都生成

### 5.4 回归基线

8 策略 baseline 报告 (json + md) 全部重新生成作为新基线 (v0.6.0-engine)。老报告归档到 `data/source/backtest_baselines/archive/v2.3.1/` 保留对比。

### 5.5 测试通过标准

- 全部新单元 + 集成测试通过
- 8 策略 baseline 报告全部生成成功
- 1 年 funding_arbitrage baseline: trades > 0, total_pnl + funding_pnl > 0

---

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 跨 leg 风险约束 `check_leg_pair` Python 不可用 (0.6.0 Phase 6) | 暂不强制 delta 中性，由 funding_arbitrage 状态机 + test_funding_arb_backtest_delta_neutral_invariant 双重保证 |
| `with_funding_schedule` 仅支持 `fixed_rate`，不能用 fixture (24 行 rate 各不同) | 用 `push_funding(perp, rate, mark, ts)` 手动按 fixture 调度，`PushFundingHelper` 封装 |
| 8 策略 baseline 报告数字会变 (之前是 baseline 自算) | 报告里加 `engine_version: 0.6.0` 标记，老报告归档到 `archive/v2.3.1/` |
| `axon_quant` 0.6.0 已装但 `uv.lock` 反映的是 test.pypi.org | `uv lock` 重新生成 lockfile，README 声明 0.6.0+ 是最低要求 |
| 8 策略模板代码 review 工作量大 | 仅 funding_arbitrage 改 on_bar，其余 7 模板不改；只改 baseline.run() 的 Action 映射逻辑 |
| `StrategyContext.settle_funding` 改为 no-op 破坏老调用 | 保留接口签名 + 返回 0.0，加 DEPRECATED 注释，文档说明 |
| 8 策略 baseline 报告首次跑可能发现新 bug | 先跑 baseline 1 个策略验证，再批量跑 8 个 |

---

## 7. 验收标准

- [ ] `uv pip install --upgrade axon-quant` 装到 0.6.0+，`uv.lock` 更新
- [ ] `axon_bridge.backtest` 模块暴露 `spot_instrument` / `swap_instrument` / `limit_order` / `PushFundingHelper`
- [ ] `BaselineBacktestService.run()` 走 `axon_quant 0.6.0` BacktestEngine
- [ ] `StrategyContext.settle_funding()` 标 DEPRECATED，行为 no-op
- [ ] `funding_arbitrage` 状态机仍正确生成 (LONG_FUNDING / SHORT_FUNDING / FLAT)
- [ ] 1 年 funding_arbitrage baseline: trades > 0, total_pnl + funding_pnl > 0
- [ ] 8 策略 baseline 报告全部重新生成
- [ ] 全部单元 + 集成测试通过 (期望 ~30 测试)
- [ ] 端到端 `check_funding_arb.py` 通过
- [ ] 老的 v2.3.1 报告归档到 `archive/v2.3.1/`
- [ ] `CHANGELOG_funding_arb.md` v2.3.2 发布

---

## 8. 不在本次范围

- ❌ 跨 leg 风险约束 Python 绑定 —— 等待 axon_quant 0.6.x 后续版本
- ❌ StreamBacktestEngine / on_tick 实时流 —— 跟 baseline 回测无关
- ❌ LLM agent / DeFi 集成 —— 跟 quant 策略无关
- ❌ `axon_bridge.oms.Order.spot/swap` 工厂改造 —— 0.4.x 兼容已够用
- ❌ 8 模板代码大幅调整 —— 只改 funding_arbitrage.on_bar

---

## 9. 时间表 (预估)

| 任务 | 工作量 |
|---|---|
| Task 1: axon_bridge.backtest 模块 + PushFundingHelper | 1.5h |
| Task 2: StrategyContext 标 DEPRECATED + funding_arbitrage 删 settle_funding | 1h |
| Task 3: BaselineBacktestService.run() 重写 + 字段扩展 | 2h |
| Task 4: 单元 + 集成测试调整 | 1.5h |
| Task 5: 8 策略 baseline 报告重新生成 | 1h |
| Task 6: scripts/check_funding_arb.py 更新 + 端到端验证 | 0.5h |
| Task 7: 文档 + CHANGELOG + uv.lock | 0.5h |
| **总计** | **8h** |

---

## 10. 引用

- axon_quant 0.6.0 multi-leg 文档: http://127.0.0.1:8000/axon_quant/zh/reference/multi-leg-backtest/
- axon_quant 0.6.0 Python bindings: http://127.0.0.1:8000/axon_quant/zh/reference/python-bindings/
- axon_quant 0.6.0 changelog: http://127.0.0.1:8000/axon_quant/zh/about/changelog/
- QuantCell axon 整合蓝图: `docs/superpowers/specs/2026-07-16-axon-quant-integration-blueprint.md`
- 上游 spec: `docs/superpowers/specs/2026-07-17-funding-arbitrage-upgrade-design.md`
- 上游 CHANGELOG: `docs/superpowers/CHANGELOG_funding_arb.md` v2.3.1
